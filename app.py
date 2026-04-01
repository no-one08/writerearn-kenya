from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
import re
from datetime import datetime, timedelta
import os
import jwt

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-this')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///writers.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
limiter = Limiter(app=app, key_func=get_remote_address)

# Email config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
mail = Mail(app)

TILL_NUMBER = "7848393"  # Your till number

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    phone = db.Column(db.String(20), unique=True, nullable=True)
    google_id = db.Column(db.String(100), unique=True, nullable=True)
    name = db.Column(db.String(100))
    password_hash = db.Column(db.String(200))
    is_verified = db.Column(db.Boolean, default=False)
    verification_code = db.Column(db.String(6))
    code_expires = db.Column(db.DateTime)
    registration_paid = db.Column(db.Boolean, default=False)
    free_tasks_used = db.Column(db.Integer, default=0)
    total_earnings = db.Column(db.Float, default=0.0)
    total_words_written = db.Column(db.Integer, default=0)
    referral_code = db.Column(db.String(10), unique=True)
    referred_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic = db.Column(db.String(200))
    content = db.Column(db.Text)
    word_count = db.Column(db.Integer)
    earnings = db.Column(db.Float, default=250.0)
    status = db.Column(db.String(20), default='pending')
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float)
    mpesa_code = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float)
    mpesa_number = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)

WRITING_TOPICS = [
    "The Impact of Artificial Intelligence on Modern Healthcare in Kenya",
    "Sustainable Living: Small Changes for a Greener Future in Nairobi",
    "The Future of Remote Work in Developing African Countries",
    "Mental Health Awareness in Kenyan Universities",
    "The Rise of Mobile Money and Financial Inclusion in East Africa",
    "Climate Change Effects on Kenyan Agriculture and Food Security",
    "Digital Marketing Strategies for Small Businesses in Kenya",
    "The Importance of Financial Literacy Among Kenyan Youth",
    "Tourism Potential and Conservation in Coastal Kenya",
    "Technology Integration in the Kenyan Education System",
    "Urbanization Challenges and Solutions in Nairobi",
    "The Growth of E-commerce and Online Shopping in Kenya",
    "Renewable Energy Solutions for Rural Kenyan Communities",
    "Women Empowerment in the African Technology Sector",
    "The Evolution of Kenyan Music and Entertainment Industry"
]

def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def generate_referral_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

@app.route('/')
def index():
    total_users = User.query.filter_by(is_verified=True).count() + 1247
    total_paid = db.session.query(db.func.sum(Withdrawal.amount)).filter_by(status='completed').scalar() or 0
    total_paid += 524750
    total_articles = Article.query.filter_by(status='approved').count() + 5680
    
    return render_template('index.html', 
                         total_users=total_users,
                         total_paid=total_paid,
                         total_articles=total_articles,
                         till_number=TILL_NUMBER)

@app.route('/api/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    data = request.json
    email = data.get('email', '').lower().strip()
    phone = data.get('phone', '').strip()
    password = data.get('password', '')
    referral = data.get('referral_code', '').upper().strip()
    
    if not email and not phone:
        return jsonify({'error': 'Email or phone required'}), 400
    
    if email and not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        return jsonify({'error': 'Invalid email format'}), 400
    
    if phone and not re.match(r'^0[17]\d{8}$', phone):
        return jsonify({'error': 'Invalid phone format. Use 07XX XXX XXX'}), 400
    
    existing = User.query.filter((User.email == email) | (User.phone == phone)).first()
    if existing:
        return jsonify({'error': 'Account already exists'}), 409
    
    code = generate_verification_code()
    user = User(
        email=email if email else None,
        phone=phone if phone else None,
        password_hash=generate_password_hash(password) if password else None,
        verification_code=code,
        code_expires=datetime.utcnow() + timedelta(minutes=10),
        referral_code=generate_referral_code()
    )
    
    if referral:
        referrer = User.query.filter_by(referral_code=referral).first()
        if referrer:
            user.referred_by = referrer.id
    
    db.session.add(user)
    db.session.commit()
    
    if email:
        try:
            msg = Message('Your WriteEarn Verification Code', 
                         sender=app.config['MAIL_USERNAME'],
                         recipients=[email])
            msg.body = f'Your verification code is: {code}\nValid for 10 minutes.'
            mail.send(msg)
        except:
            pass
    
    return jsonify({
        'message': 'Verification code sent', 
        'code': code
    }), 200

@app.route('/api/verify', methods=['POST'])
def verify():
    data = request.json
    code = data.get('code', '')
    email = data.get('email', '').lower().strip()
    phone = data.get('phone', '').strip()
    
    user = User.query.filter(
        ((User.email == email) | (User.phone == phone)) &
        (User.verification_code == code)
    ).first()
    
    if not user:
        return jsonify({'error': 'Invalid code'}), 400
    
    if datetime.utcnow() > user.code_expires:
        return jsonify({'error': 'Code expired'}), 400
    
    user.is_verified = True
    user.verification_code = None
    db.session.commit()
    
    token = jwt.encode({'user_id': user.id, 'exp': datetime.utcnow() + timedelta(days=7)}, 
                       app.config['SECRET_KEY'], algorithm='HS256')
    
    return jsonify({
        'message': 'Verified successfully',
        'token': token,
        'free_tasks_remaining': 2 - user.free_tasks_used,
        'is_registered': user.registration_paid,
        'referral_code': user.referral_code
    }), 200

@app.route('/api/dashboard', methods=['GET'])
def dashboard():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Not authenticated'}), 401
    
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(payload['user_id'])
    except:
        return jsonify({'error': 'Invalid token'}), 401
    
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    articles = Article.query.filter_by(user_id=user.id).order_by(Article.submitted_at.desc()).all()
    referral_count = User.query.filter_by(referred_by=user.id).count()
    
    return jsonify({
        'name': user.name or 'Writer',
        'email': user.email,
        'total_earnings': user.total_earnings,
        'total_words': user.total_words_written,
        'articles_count': len(articles),
        'free_tasks_used': user.free_tasks_used,
        'is_registered': user.registration_paid,
        'can_withdraw': user.registration_paid and user.total_earnings >= 1000,
        'referral_code': user.referral_code,
        'referral_count': referral_count,
        'referral_earnings': referral_count * 50,
        'articles': [{
            'id': a.id,
            'topic': a.topic,
            'word_count': a.word_count,
            'earnings': a.earnings,
            'status': a.status,
            'date': a.submitted_at.strftime('%Y-%m-%d')
        } for a in articles]
    }), 200

@app.route('/api/get-topic', methods=['GET'])
def get_topic():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Not authenticated'}), 401
    
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(payload['user_id'])
    except:
        return jsonify({'error': 'Invalid token'}), 401
    
    if user.free_tasks_used >= 2 and not user.registration_paid:
        return jsonify({
            'error': 'Please pay registration fee to continue',
            'requires_payment': True,
            'amount': 350,
            'till_number': TILL_NUMBER
        }), 403
    
    topic = random.choice(WRITING_TOPICS)
    
    return jsonify({
        'topic': topic,
        'min_words': 300,
        'max_words': 500,
        'payment_per_article': 250,
        'free_tasks_remaining': max(0, 2 - user.free_tasks_used)
    }), 200

@app.route('/api/submit-article', methods=['POST'])
def submit_article():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Not authenticated'}), 401
    
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(payload['user_id'])
    except:
        return jsonify({'error': 'Invalid token'}), 401
    
    data = request.json
    content = data.get('content', '').strip()
    topic = data.get('topic', '').strip()
    
    word_count = len(content.split())
    
    if word_count < 300:
        return jsonify({'error': f'Article too short. Minimum 300 words. Current: {word_count}'}), 400
    if word_count > 500:
        return jsonify({'error': f'Article too long. Maximum 500 words. Current: {word_count}'}), 400
    
    if user.free_tasks_used >= 2 and not user.registration_paid:
        return jsonify({
            'error': 'Registration fee required',
            'requires_payment': True,
            'amount': 350,
            'till_number': TILL_NUMBER
        }), 403
    
    is_free_task = user.free_tasks_used < 2
    earnings = 0.0 if is_free_task else 250.0
    
    article = Article(
        user_id=user.id,
        topic=topic,
        content=content,
        word_count=word_count,
        earnings=earnings,
        status='pending'
    )
    
    user.free_tasks_used += 1
    user.total_words_written += word_count
    if user.registration_paid and not is_free_task:
        user.total_earnings += earnings
    
    db.session.add(article)
    db.session.commit()
    
    return jsonify({
        'message': 'Article submitted successfully',
        'earnings': earnings,
        'total_earnings': user.total_earnings,
        'free_tasks_used': user.free_tasks_used
    }), 200

@app.route('/api/payment', methods=['POST'])
def process_payment():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Not authenticated'}), 401
    
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(payload['user_id'])
    except:
        return jsonify({'error': 'Invalid token'}), 401
    
    data = request.json
    mpesa_code = data.get('mpesa_code', '').upper().strip()
    
    if not re.match(r'^[A-Z0-9]{8,12}$', mpesa_code):
        return jsonify({'error': 'Invalid M-Pesa code format'}), 400
    
    existing = Payment.query.filter_by(mpesa_code=mpesa_code).first()
    if existing:
        return jsonify({'error': 'M-Pesa code already used'}), 400
    
    payment = Payment(
        user_id=user.id,
        amount=350.0,
        mpesa_code=mpesa_code,
        status='completed'
    )
    
    user.registration_paid = True
    db.session.add(payment)
    db.session.commit()
    
    return jsonify({
        'message': 'Payment verified successfully',
        'status': 'completed'
    }), 200

@app.route('/api/withdraw', methods=['POST'])
def request_withdrawal():
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return jsonify({'error': 'Not authenticated'}), 401
    
    token = auth_header.split(' ')[1]
    try:
        payload = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
        user = User.query.get(payload['user_id'])
    except:
        return jsonify({'error': 'Invalid token'}), 401
    
    if not user.registration_paid:
        return jsonify({'error': 'Complete registration to withdraw'}), 403
    
    data = request.json
    amount = float(data.get('amount', 0))
    mpesa_number = data.get('mpesa_number', '').strip()
    
    if amount < 1000:
        return jsonify({'error': 'Minimum withdrawal is Ksh 1,000'}), 400
    if amount > user.total_earnings:
        return jsonify({'error': 'Insufficient balance'}), 400
    if not re.match(r'^0[17]\d{8}$', mpesa_number):
        return jsonify({'error': 'Invalid M-Pesa number'}), 400
    
    withdrawal = Withdrawal(
        user_id=user.id,
        amount=amount,
        mpesa_number=mpesa_number,
        status='pending'
    )
    
    user.total_earnings -= amount
    db.session.add(withdrawal)
    db.session.commit()
    
    return jsonify({
        'message': 'Withdrawal request submitted',
        'amount': amount,
        'status': 'pending',
        'estimated_time': '24-48 hours'
    }), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)