from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from flask_login import login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
from models import User

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            session.permanent = True  # Use permanent session
            session['last_active'] = datetime.utcnow()
            flash('Login berhasil! Selamat datang kembali.', 'success')
            return redirect(url_for('dashboard'))
        else:
            error = "Username atau password salah. Silakan coba lagi."
    
    return render_template('login.html', error=error)

@auth_bp.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.before_request
def check_session_timeout():
    if current_user.is_authenticated:
        last_active = session.get('last_active')
        if last_active:
            last_active = datetime.fromisoformat(str(last_active))
            session_timeout = timedelta(minutes=30)
            if datetime.utcnow() - last_active > session_timeout:
                session.clear()
                logout_user()
                return redirect(url_for('auth.login'))
