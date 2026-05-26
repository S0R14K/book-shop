import re

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ..models.user import User

auth_bp = Blueprint('auth', __name__)


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get("user_id"):
        return redirect(url_for("shop.home"))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not EMAIL_RE.match(email):
            flash("Please enter a valid email address.", "error")
            return render_template('register.html', email=email, errors={"email": "Use a valid email address."})

        if len(password) < 8:
            flash("Password must be at least 8 characters long.", "error")
            return render_template('register.html', email=email, errors={"password": "Use at least 8 characters."})

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template('register.html', email=email, errors={"confirm_password": "Passwords must match."})

        existing = User.find_by_email(email)
        if existing:
            flash("Email already registered.", "error")
            return render_template('register.html', email=email, errors={"email": "This email is already registered."})

        User.create(email, password)
        flash("Registration successful! Please log in.", "success")
        return redirect(url_for('auth.login'))

    return render_template('register.html', errors={})


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get("user_id"):
        return redirect(url_for("shop.home"))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.find_by_email(email)
        if user and User.check_password(user['password_hash'], password):
            session.clear()
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            session['is_admin'] = bool(user['is_admin'])
            session.permanent = True
            flash("Logged in successfully!", "success")
            return redirect(request.args.get("next") or url_for('shop.home'))

        flash("Invalid email or password.", "error")
        return render_template('login.html', email=email, errors={"password": "Check your email and password."})

    return render_template('login.html', errors={})


@auth_bp.route('/logout')
def logout():
    session.clear()
    flash("Logged out.", "success")
    return redirect(url_for('shop.home'))
