// Add to your existing JavaScript

// Enhanced registration with password and referral
document.getElementById('registerForm')?.addEventListener('submit', function(e) {
    e.preventDefault();
    const email = document.getElementById('regEmail').value;
    const phone = document.getElementById('regPhone').value;
    const password = document.getElementById('regPassword').value;
    const referral = document.getElementById('referralInput').value;
    const recaptchaToken = grecaptcha.getResponse();
    
    if (!recaptchaToken) {
        alert('Please complete the reCAPTCHA');
        return;
    }
    
    if (password.length < 8) {
        alert('Password must be at least 8 characters');
        return;
    }
    
    fetch('/api/register', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            email, 
            phone, 
            password,
            referral_code: referral,
            recaptcha_token: recaptchaToken
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.message) {
            document.getElementById('registerForm').style.display = 'none';
            document.getElementById('verifyForm').style.display = 'flex';
            document.getElementById('verifyTarget').textContent = 
                data.email_masked || data.phone_masked;
        } else {
            alert(data.error);
            grecaptcha.reset();
        }
    });
});

// Enhanced payment processing with status checking
function processPayment(e) {
    e.preventDefault();
    const code = document.getElementById('mpesaCode').value;
    
    document.getElementById('payBtnText').style.display = 'none';
    document.getElementById('paySpinner').style.display = 'inline-block';
    document.getElementById('paymentStatus').style.display = 'block';
    
    fetch('/api/payment', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + localStorage.getItem('token')
        },
        body: JSON.stringify({mpesa_code: code})
    })
    .then(res => res.json())
    .then(data => {
        if (data.message) {
            // Start status polling
            pollPaymentStatus();
        } else {
            alert(data.error);
            resetPaymentForm();
        }
    });
}

function pollPaymentStatus() {
    const checkStatus = setInterval(() => {
        fetch('/api/check-payment-status', {
            headers: {'Authorization': 'Bearer ' + localStorage.getItem('token')}
        })
        .then(res => res.json())
        .then(data => {
            updatePaymentUI(data.status);
            
            if (data.status === 'completed') {
                clearInterval(checkStatus);
                setTimeout(() => {
                    document.getElementById('paymentModal').style.display = 'none';
                    loadDashboardData();
                    alert('🎉 Payment verified! You are now a Premium Writer!');
                }, 1500);
            } else if (data.status === 'failed') {
                clearInterval(checkStatus);
                alert('Payment verification failed. Please contact support.');
                resetPaymentForm();
            }
        });
    }, 3000);
    
    // Stop polling after 2 minutes
    setTimeout(() => clearInterval(checkStatus), 120000);
}

function updatePaymentUI(status) {
    const steps = ['step1', 'step2', 'step3'];
    const messages = {
        'processing': 'Payment received, verifying...',
        'pending': 'Confirming with M-Pesa...',
        'completed': 'Payment verified!',
        'failed': 'Verification failed'
    };
    
    document.getElementById('statusMessage').textContent = messages[status] || 'Processing...';
    
    if (status === 'processing') {
        document.getElementById('step1').classList.add('active');
    } else if (status === 'pending') {
        document.getElementById('step1').classList.add('active');
        document.getElementById('step2').classList.add('active');
    } else if (status === 'completed') {
        steps.forEach(s => document.getElementById(s).classList.add('active'));
    }
}

// Withdrawal functions
function showWithdrawModal() {
    fetch('/api/dashboard', {
        headers: {'Authorization': 'Bearer ' + localStorage.getItem('token')}
    })
    .then(res => res.json())
    .then(data => {
        document.getElementById('withdrawBalance').textContent = `Ksh ${data.total_earnings}`;
        document.getElementById('withdrawAmount').max = data.total_earnings;
        document.getElementById('withdrawModal').style.display = 'block';
    });
}

function processWithdrawal(e) {
    e.preventDefault();
    const amount = document.getElementById('withdrawAmount').value;
    const phone = document.getElementById('withdrawPhone').value;
    
    fetch('/api/withdraw', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + localStorage.getItem('token')
        },
        body: JSON.stringify({
            amount: parseFloat(amount),
            mpesa_number: phone
        })
    })
    .then(res => res.json())
    .then(data => {
        if (data.message) {
            alert(`✓ ${data.message}\nEstimated time: ${data.estimated_time}`);
            document.getElementById('withdrawModal').style.display = 'none';
            loadDashboardData();
        } else {
            alert(data.error);
        }
    });
}

// Load referral data in dashboard
function loadDashboardData() {
    fetch('/api/dashboard', {
        headers: {'Authorization': 'Bearer ' + localStorage.getItem('token')}
    })
    .then(res => res.json())
    .then(data => {
        // ... existing code ...
        
        // Update referral section
        if (data.referral_code) {
            document.getElementById('referralBox').style.display = 'flex';
            document.getElementById('referralCode').textContent = data.referral_code;
            document.getElementById('referralStats').style.display = 'flex';
            document.getElementById('refCount').textContent = data.referral_count;
            document.getElementById('refEarnings').textContent = `Ksh ${data.referral_earnings}`;
        }
        
        // Update withdrawals list
        if (data.withdrawals && data.withdrawals.length > 0) {
            // Add withdrawals to UI
        }
    });
}

function copyReferral() {
    const code = document.getElementById('referralCode').textContent;
    navigator.clipboard.writeText(code).then(() => {
        alert('Referral code copied! Share with friends to earn Ksh 50 each.');
    });
}

// Check auth with token
function checkAuth() {
    const token = localStorage.getItem('token');
    if (!token) return;
    
    fetch('/api/dashboard', {
        headers: {'Authorization': 'Bearer ' + token}
    })
    .then(res => {
        if (res.ok) {
            closeAuthModal();
            showDashboard();
            loadDashboardData();
        } else {
            localStorage.removeItem('token');
        }
    })
    .catch(() => localStorage.removeItem('token'));
}

// Update all fetch calls to include token
const originalFetch = window.fetch;
window.fetch = function(...args) {
    if (args[1] && args[1].headers && !args[1].headers['Authorization']) {
        const token = localStorage.getItem('token');
        if (token) {
            args[1].headers['Authorization'] = 'Bearer ' + token;
        }
    }
    return originalFetch.apply(this, args);
};
