from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from werkzeug.security import generate_password_hash, check_password_hash
import random
import string
import json
import re
import requests
from datetime import datetime, timedelta
import os
from functools import wraps
import jwt
import bleach

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///writers.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

# Security headers
Talisman(app, force_https=False)  # Set True in production

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

db = SQLAlchemy(app)

# Email config
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
mail = Mail(app)

# reCAPTCHA config
RECAPTCHA_SECRET = os.environ.get('RECAPTCHA_SECRET_KEY')

# JWT config
JWT_SECRET = os.environ.get('JWT_SECRET', app.config['SECRET_KEY'])

# Database Models
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
    is_registered = db.Column(db.Boolean, default=False)
    registration_paid = db.Column(db.Boolean, default=False)
    free_tasks_used = db.Column(db.Integer, default=0)
    total_earnings = db.Column(db.Float, default=0.0)
    total_words_written = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    failed_logins = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime)
    referral_code = db.Column(db.String(10), unique=True)
    referred_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    articles = db.relationship('Article', backref='author', lazy=True)
    withdrawals = db.relationship('Withdrawal', backref='user', lazy=True)
    referrals = db.relationship('User', backref=db.backref('referrer', remote_side=[id]))

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic = db.Column(db.String(200))
    content = db.Column(db.Text)
    word_count = db.Column(db.Integer)
    earnings = db.Column(db.Float, default=250.0)
    status = db.Column(db.String(20), default='pending')
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.Integer)
    ai_score = db.Column(db.Float)
    plagiarism_score = db.Column(db.Float)
    feedback = db.Column(db.Text)
    revisions_count = db.Column(db.Integer, default=0)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float)
    mpesa_code = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime)

class Withdrawal(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float)
    mpesa_number = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    processed_at = db.Column(db.DateTime)
    transaction_id = db.Column(db.String(50))

class Admin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(200))
    is_super = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime)

class SystemConfig(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(50), unique=True)
    value = db.Column(db.String(500))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

# Writing topics
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
    "The Evolution of Kenyan Music and Entertainment Industry",
    "Challenges Facing Kenyan SMEs in the Digital Age",
    "The Role of Youth in Kenyan Politics and Governance",
    "Sports Development and Talent Nurturing in Kenya",
    "Real Estate Trends in Major Kenyan Cities",
    "The Future of Public Transport in Nairobi"
]

def generate_verification_code():
    return ''.join(random.choices(string.digits, k=6))

def generate_referral_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def sanitize_input(text):
    if not text:
        return ""
    return bleach.clean(text.strip(), tags=[], strip=True)

def verify_recaptcha(token):
    if not RECAPTCHA_SECRET:
        return True
    try:
        response = requests.post(
            'https://www.google.com/recaptcha/api/siteverify',
            data={'secret': RECAPTCHA_SECRET, 'response': token},
            timeout=5
        )
        return response.json().get('success', False)
    except:
        return False

def generate_jwt(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(days=7),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def verify_jwt(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload['user_id']
    except:
        return None

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token.split(' ')[1]
            user_id = verify_jwt(token)
            if user_id:
                user = User.query.get(user_id)
                if user and user.is_active:
                    request.current_user = user
                    return f(*args, **kwargs)
        return jsonify({'error': 'Authentication required'}), 401
    return decorated_function

def check_account_lock(user):
    if user.locked_until and datetime.utcnow() < user.locked_until:
        return False
    if user.locked_until and datetime.utcnow() >= user.locked_until:
        user.locked_until = None
        user.failed_logins = 0
        db.session.commit()
    return True

@app.route('/')
def index():
    total_users = User.query.filter_by(is_verified=True).count() + 1247
    total_paid = db.session.query(db.func.sum(Withdrawal.amount)).filter_by(status='completed').scalar() or 0
    total_paid += 524750
    total_articles = Article.query.filter_by(status='approved').count() + 5680
    
    return render_template('index.html', 
                         total_users=total_users,
                         total_paid=total_paid,
                         total_articles=total_articles)

@app.route('/api/register', methods=['POST'])
@limiter.limit("5 per minute")
def register():
    data = request.json
    email = sanitize_input(data.get('email', '')).lower()
    phone = sanitize_input(data.get('phone', ''))
    password = data.get('password', '')
    recaptcha_token = data.get('recaptcha_token', '')
    referral_code = sanitize_input(data.get('referral_code', ''))
    
    if not verify_recaptcha(recaptcha_token):
        return jsonify({'error': 'reCAPTCHA verification failed'}), 400
    
    if not email and not phone:
        return jsonify({'error': 'Email or phone required'}), 400
    
    if email and not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
        return jsonify({'error': 'Invalid email format'}), 400
    
    if phone and not re.match(r'^0[17]\d{8}$', phone):
        return jsonify({'error': 'Invalid phone format. Use 07XX XXX XXX or 01XX XXX XXX'}), 400
    
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
    
    if referral_code:
        referrer = User.query.filter_by(referral_code=referral_code.upper()).first()
        if referrer:
            user.referred_by = referrer.id
    
    db.session.add(user)
    db.session.commit()
    
    # Send verification code
    if email:
        try:
            msg = Message('Your WriteEarn Verification Code', 
                         sender=app.config['MAIL_USERNAME'],
                         recipients=[email])
            msg.body = f'Your verification code is: {code}\nValid for 10 minutes.\n\nIf you did not request this, please ignore.'
            mail.send(msg)
        except Exception as e:
            app.logger.error(f"Email failed: {e}")
    
    # TODO: Integrate SMS gateway for phone verification
    
    return jsonify({
        'message': 'Verification code sent', 
        'email_masked': mask_email(email) if email else None,
        'phone_masked': mask_phone(phone) if phone else None
    }), 200

def mask_email(email):
    if not email:
        return None
    parts = email.split('@')
    return parts[0][:2] + '***@' + parts[1]

def mask_phone(phone):
    if not phone:
        return None
    return phone[:4] + '****' + phone[-3:]

@app.route('/api/verify', methods=['POST'])
@limiter.limit("10 per minute")
def verify():
    data = request.json
    code = sanitize_input(data.get('code', ''))
    email = sanitize_input(data.get('email', '')).lower()
    phone = sanitize_input(data.get('phone', ''))
    
    user = User.query.filter(
        ((User.email == email) | (User.phone == phone)) &
        (User.verification_code == code)
    ).first()
    
    if not user:
        return jsonify({'error': 'Invalid code'}), 400
    
    if datetime.utcnow() > user.code_expires:
        return jsonify({'error': 'Code expired. Please request new code.'}), 400
    
    user.is_verified = True
    user.verification_code = None
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    token = generate_jwt(user.id)
    
    return jsonify({
        'message': 'Verified successfully',
        'token': token,
        'free_tasks_remaining': 2 - user.free_tasks_used,
        'is_registered': user.registration_paid,
        'referral_code': user.referral_code
    }), 200

@app.route('/api/resend-code', methods=['POST'])
@limiter.limit("3 per hour")
def resend_code():
    data = request.json
    email = sanitize_input(data.get('email', '')).lower()
    phone = sanitize_input(data.get('phone', ''))
    
    user = User.query.filter((User.email == email) | (User.phone == phone)).first()
    if not user:
        return jsonify({'error': 'Account not found'}), 404
    
    if user.is_verified:
        return jsonify({'error': 'Account already verified'}), 400
    
    code = generate_verification_code()
    user.verification_code = code
    user.code_expires = datetime.utcnow() + timedelta(minutes=10)
    db.session.commit()
    
    if user.email:
        try:
            msg = Message('Your New WriteEarn Verification Code', 
                         sender=app.config['MAIL_USERNAME'],
                         recipients=[user.email])
            msg.body = f'Your new verification code is: {code}\nValid for 10 minutes.'
            mail.send(msg)
        except Exception as e:
            app.logger.error(f"Resend email failed: {e}")
    
    return jsonify({'message': 'New code sent'}), 200

@app.route('/api/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.json
    email = sanitize_input(data.get('email', '')).lower()
    password = data.get('password', '')
    recaptcha_token = data.get('recaptcha_token', '')
    
    if not verify_recaptcha(recaptcha_token):
        return jsonify({'error': 'reCAPTCHA verification failed'}), 400
    
    user = User.query.filter_by(email=email).first()
    
    if not user or not user.password_hash:
        return jsonify({'error': 'Invalid credentials'}), 401
    
    if not check_account_lock(user):
        remaining = int((user.locked_until - datetime.utcnow()).total_seconds() / 60)
        return jsonify({'error': f'Account locked. Try again in {remaining} minutes.'}), 403
    
    if not check_password_hash(user.password_hash, password):
        user.failed_logins += 1
        if user.failed_logins >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=30)
        db.session.commit()
        return jsonify({'error': 'Invalid credentials'}), 401
    
    user.failed_logins = 0
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    token = generate_jwt(user.id)
    
    return jsonify({
        'message': 'Login successful',
        'token': token,
        'free_tasks_remaining': 2 - user.free_tasks_used,
        'is_registered': user.registration_paid,
        'referral_code': user.referral_code
    }), 200

@app.route('/api/google-auth', methods=['POST'])
def google_auth():
    data = request.json
    google_id = data.get('google_id')
    email = sanitize_input(data.get('email', '')).lower()
    name = sanitize_input(data.get('name', ''))
    
    user = User.query.filter_by(google_id=google_id).first()
    if not user:
        existing = User.query.filter_by(email=email).first()
        if existing:
            existing.google_id = google_id
            existing.name = name or existing.name
            db.session.commit()
            user = existing
        else:
            user = User(
                google_id=google_id,
                email=email,
                name=name,
                is_verified=True,
                referral_code=generate_referral_code(),
                last_login=datetime.utcnow()
            )
            db.session.add(user)
            db.session.commit()
    
    user.last_login = datetime.utcnow()
    db.session.commit()
    
    token = generate_jwt(user.id)
    
    return jsonify({
        'message': 'Login successful',
        'token': token,
        'free_tasks_remaining': 2 - user.free_tasks_used,
        'is_registered': user.registration_paid,
        'referral_code': user.referral_code
    }), 200

@app.route('/api/get-topic', methods=['GET'])
@login_required
def get_topic():
    user = request.current_user
    
    if user.free_tasks_used >= 2 and not user.registration_paid:
        return jsonify({
            'error': 'Please pay registration fee to continue',
            'requires_payment': True,
            'amount': 350
        }), 403
    
    # Get topics user hasn't written about recently
    recent_topics = [a.topic for a in Article.query.filter_by(user_id=user.id)
                    .order_by(Article.submitted_at.desc()).limit(5).all()]
    
    available_topics = [t for t in WRITING_TOPICS if t not in recent_topics]
    if not available_topics:
        available_topics = WRITING_TOPICS
    
    topic = random.choice(available_topics)
    
    return jsonify({
        'topic': topic,
        'min_words': 300,
        'max_words': 500,
        'payment_per_article': 250,
        'free_tasks_remaining': max(0, 2 - user.free_tasks_used),
        'is_premium': user.registration_paid
    }), 200

@app.route('/api/submit-article', methods=['POST'])
@login_required
@limiter.limit("10 per hour")
def submit_article():
    user = request.current_user
    data = request.json
    content = sanitize_input(data.get('content', ''))
    topic = sanitize_input(data.get('topic', ''))
    
    if not content or not topic:
        return jsonify({'error': 'Content and topic required'}), 400
    
    word_count = len(content.split())
    
    if word_count < 300:
        return jsonify({
            'error': f'Article too short. Minimum 300 words. Current: {word_count}',
            'word_count': word_count,
            'needed': 300 - word_count
        }), 400
    
    if word_count > 500:
        return jsonify({
            'error': f'Article too long. Maximum 500 words. Current: {word_count}',
            'word_count': word_count,
            'excess': word_count - 500
        }), 400
    
    if user.free_tasks_used >= 2 and not user.registration_paid:
        return jsonify({
            'error': 'Registration fee required',
            'requires_payment': True,
            'amount': 350
        }), 403
    
    # Check for duplicate content
    existing = Article.query.filter_by(user_id=user.id, content=content).first()
    if existing:
        return jsonify({'error': 'Duplicate submission detected'}), 400
    
    # Calculate earnings
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
        'article_id': article.id,
        'earnings': earnings,
        'total_earnings': user.total_earnings,
        'words_written': word_count,
        'status': 'pending_review',
        'is_free_task': is_free_task,
        'free_tasks_used': user.free_tasks_used,
        'free_tasks_remaining': max(0, 2 - user.free_tasks_used)
    }), 200

@app.route('/api/payment', methods=['POST'])
@login_required
def process_payment():
    user = request.current_user
    data = request.json
    mpesa_code = sanitize_input(data.get('mpesa_code', '')).upper()
    
    if not re.match(r'^[A-Z0-9]{8,12}$', mpesa_code):
        return jsonify({'error': 'Invalid M-Pesa code format'}), 400
    
    existing = Payment.query.filter_by(mpesa_code=mpesa_code).first()
    if existing:
        return jsonify({'error': 'M-Pesa code already used'}), 400
    
    payment = Payment(
        user_id=user.id,
        amount=350.0,
        mpesa_code=mpesa_code,
        status='processing'
    )
    
    db.session.add(payment)
    db.session.commit()
    
    return jsonify({
        'message': 'Payment received and processing',
        'status': 'processing',
        'amount': 350,
        'payment_id': payment.id
    }), 200

@app.route('/api/check-payment-status', methods=['GET'])
@login_required
def check_payment_status():
    user = request.current_user
    payment = Payment.query.filter_by(user_id=user.id).order_by(Payment.created_at.desc()).first()
    
    if not payment:
        return jsonify({'status': 'none'}), 404
    
    return jsonify({
        'status': payment.status,
        'amount': payment.amount,
        'created_at': payment.created_at.isoformat()
    }), 200

@app.route('/api/withdraw', methods=['POST'])
@login_required
def request_withdrawal():
    user = request.current_user
    data = request.json
    amount = float(data.get('amount', 0))
    mpesa_number = sanitize_input(data.get('mpesa_number', ''))
    
    if not user.registration_paid:
        return jsonify({'error': 'Complete registration to withdraw'}), 403
    
    if amount < 1000:
        return jsonify({'error': 'Minimum withdrawal is Ksh 1,000'}), 400
    
    if amount > user.total_earnings:
        return jsonify({'error': 'Insufficient balance'}), 400
    
    if not re.match(r'^0[17]\d{8}$', mpesa_number):
        return jsonify({'error': 'Invalid M-Pesa number'}), 400
    
    # Check pending withdrawals
    pending = Withdrawal.query.filter_by(user_id=user.id, status='pending').first()
    if pending:
        return jsonify({'error': 'You have a pending withdrawal request'}), 400
    
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
        'withdrawal_id': withdrawal.id,
        'amount': amount,
        'status': 'pending',
        'estimated_time': '24-48 hours'
    }), 200

@app.route('/api/dashboard', methods=['GET'])
@login_required
def dashboard():
    user = request.current_user
    articles = Article.query.filter_by(user_id=user.id).order_by(Article.submitted_at.desc()).all()
    
    # Calculate referral earnings
    referral_count = User.query.filter_by(referred_by=user.id).count()
    referral_earnings = referral_count * 50  # Ksh 50 per referral
    
    return jsonify({
        'name': user.name or 'Writer',
        'email': user.email,
        'phone': user.phone,
        'total_earnings': user.total_earnings,
        'total_words': user.total_words_written,
        'articles_count': len(articles),
        'approved_count': len([a for a in articles if a.status == 'approved']),
        'pending_count': len([a for a in articles if a.status == 'pending']),
        'free_tasks_used': user.free_tasks_used,
        'is_registered': user.registration_paid,
        'can_withdraw': user.registration_paid and user.total_earnings >= 1000,
        'min_withdrawal': 1000,
        'referral_code': user.referral_code,
        'referral_count': referral_count,
        'referral_earnings': referral_earnings,
        'articles': [{
            'id': a.id,
            'topic': a.topic,
            'word_count': a.word_count,
            'earnings': a.earnings,
            'status': a.status,
            'date': a.submitted_at.strftime('%Y-%m-%d'),
            'feedback': a.feedback
        } for a in articles],
        'withdrawals': [{
            'id': w.id,
            'amount': w.amount,
            'status': w.status,
            'date': w.requested_at.strftime('%Y-%m-%d')
        } for w in user.withdrawals]
    }), 200

@app.route('/api/logout', methods=['POST'])
def logout():
    return jsonify({'message': 'Logged out successfully'}), 200

# Admin routes
@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.json
    username = sanitize_input(data.get('username', ''))
    password = data.get('password', '')
    
    admin = Admin.query.filter_by(username=username).first()
    if not admin or not check_password_hash(admin.password_hash, password):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    admin.last_login = datetime.utcnow()
    db.session.commit()
    
    token = generate_jwt(admin.id)
    return jsonify({'token': token, 'is_super': admin.is_super}), 200

@app.route('/admin/articles', methods=['GET'])
def get_pending_articles():
    articles = Article.query.filter_by(status='pending').order_by(Article.submitted_at.asc()).all()
    return jsonify([{
        'id': a.id,
        'topic': a.topic,
        'content': a.content,
        'word_count': a.word_count,
        'author': a.author.name or a.author.email,
        'submitted_at': a.submitted_at.isoformat()
    } for a in articles]), 200

@app.route('/admin/review-article', methods=['POST'])
def review_article():
    data = request.json
    article_id = data.get('article_id')
    decision = data.get('decision')  # 'approve' or 'reject'
    feedback = sanitize_input(data.get('feedback', ''))
    
    article = Article.query.get(article_id)
    if not article:
        return jsonify({'error': 'Article not found'}), 404
    
    if decision == 'approve':
        article.status = 'approved'
        article.author.total_earnings += article.earnings
    else:
        article.status = 'rejected'
        article.feedback = feedback
    
    article.reviewed_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'message': f'Article {decision}d'}), 200

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        
        # Create default admin if none exists
        if not Admin.query.first():
            admin = Admin(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                is_super=True
            )
            db.session.add(admin)
            db.session.commit()
    
    app.run(debug=True)
