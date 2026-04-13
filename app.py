"""
Aplikasi Pengelola Keuangan & Tabungan
Flask-based Financial Management Application
"""

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
from functools import wraps
import os
import json
import calendar

# ─── App Configuration ───────────────────────────────────────────────────────

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'tabungan-secret-key-2026')

# Deteksi DATABASE_URL untuk layanan cloud seperti Vercel (PostgreSQL)
database_url = os.environ.get('DATABASE_URL', 'sqlite:///keuangan.db')
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Silakan login terlebih dahulu.'
login_manager.login_message_category = 'info'

# ─── Database Models ─────────────────────────────────────────────────────────


class User(UserMixin, db.Model):
    """Model untuk pengguna."""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    transactions = db.relationship('Transaction', backref='user', lazy=True, cascade='all, delete-orphan')
    savings_goals = db.relationship('SavingsGoal', backref='user', lazy=True, cascade='all, delete-orphan')
    categories = db.relationship('Category', backref='user', lazy=True, cascade='all, delete-orphan')
    budgets = db.relationship('Budget', backref='user', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    """Model untuk kategori transaksi."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'income' or 'expense'
    icon = db.Column(db.String(50), default='fas fa-tag')
    color = db.Column(db.String(20), default='#6C5CE7')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    transactions = db.relationship('Transaction', backref='category', lazy=True)

    def __repr__(self):
        return f'<Category {self.name}>'


class Transaction(db.Model):
    """Model untuk transaksi pemasukan/pengeluaran."""
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(20), nullable=False)  # 'income' or 'expense'
    description = db.Column(db.String(200))
    date = db.Column(db.Date, nullable=False, default=date.today)
    payment_method = db.Column(db.String(20), nullable=False, default='Tunai') # 'Tunai' or 'M-Banking'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=True)

    def __repr__(self):
        return f'<Transaction {self.type} {self.amount}>'


class SavingsGoal(db.Model):
    """Model untuk target tabungan."""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, default=0.0)
    deadline = db.Column(db.Date, nullable=True)
    icon = db.Column(db.String(50), default='fas fa-piggy-bank')
    color = db.Column(db.String(20), default='#00B894')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    deposits = db.relationship('SavingsDeposit', backref='goal', lazy=True, cascade='all, delete-orphan')

    @property
    def progress_percent(self):
        if self.target_amount <= 0:
            return 0
        pct = (self.current_amount / self.target_amount) * 100
        return min(pct, 100)

    @property
    def remaining(self):
        return max(self.target_amount - self.current_amount, 0)


class SavingsDeposit(db.Model):
    """Model untuk riwayat setoran tabungan."""
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    depositor_name = db.Column(db.String(100))
    note = db.Column(db.String(200))
    date = db.Column(db.Date, nullable=False, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    goal_id = db.Column(db.Integer, db.ForeignKey('savings_goal.id'), nullable=False)


class Budget(db.Model):
    """Model untuk anggaran bulanan."""
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    month = db.Column(db.Integer, nullable=False)  # 1-12
    year = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    category = db.relationship('Category', backref='budgets_rel')


# ─── Login Manager ───────────────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ─── Template Filters ────────────────────────────────────────────────────────

@app.template_filter('currency')
def currency_filter(value):
    """Format angka ke format Rupiah."""
    try:
        value = float(value)
        if value >= 0:
            return f"Rp {value:,.0f}".replace(",", ".")
        else:
            return f"-Rp {abs(value):,.0f}".replace(",", ".")
    except (ValueError, TypeError):
        return "Rp 0"


@app.template_filter('date_format')
def date_format_filter(value, fmt='%d %B %Y'):
    """Format tanggal."""
    if isinstance(value, str):
        try:
            value = datetime.strptime(value, '%Y-%m-%d').date()
        except ValueError:
            return value
    if value:
        # Indonesian month names
        months_id = {
            1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
            5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
            9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
        }
        day = value.day
        month = months_id.get(value.month, '')
        year = value.year
        return f"{day} {month} {year}"
    return ''


@app.template_filter('short_date')
def short_date_filter(value):
    """Format tanggal singkat."""
    if value:
        months_id = {
            1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
            5: 'Mei', 6: 'Jun', 7: 'Jul', 8: 'Agu',
            9: 'Sep', 10: 'Okt', 11: 'Nov', 12: 'Des'
        }
        if isinstance(value, str):
            try:
                value = datetime.strptime(value, '%Y-%m-%d').date()
            except ValueError:
                return value
        day = value.day
        month = months_id.get(value.month, '')
        return f"{day} {month}"
    return ''


# ─── Helper Functions ─────────────────────────────────────────────────────────

def create_default_categories(user_id):
    """Buat kategori default untuk user baru."""
    income_categories = [
        {'name': 'Gaji', 'icon': 'fas fa-briefcase', 'color': '#00B894'},
        {'name': 'Freelance', 'icon': 'fas fa-laptop-code', 'color': '#00CEC9'},
        {'name': 'Investasi', 'icon': 'fas fa-chart-line', 'color': '#0984E3'},
        {'name': 'Bonus', 'icon': 'fas fa-gift', 'color': '#6C5CE7'},
        {'name': 'Lainnya', 'icon': 'fas fa-plus-circle', 'color': '#A29BFE'},
    ]
    expense_categories = [
        {'name': 'Makanan & Minuman', 'icon': 'fas fa-utensils', 'color': '#E17055'},
        {'name': 'Transportasi', 'icon': 'fas fa-car', 'color': '#FDCB6E'},
        {'name': 'Belanja', 'icon': 'fas fa-shopping-bag', 'color': '#E84393'},
        {'name': 'Tagihan', 'icon': 'fas fa-file-invoice', 'color': '#D63031'},
        {'name': 'Hiburan', 'icon': 'fas fa-gamepad', 'color': '#FD79A8'},
        {'name': 'Kesehatan', 'icon': 'fas fa-heartbeat', 'color': '#55EFC4'},
        {'name': 'Pendidikan', 'icon': 'fas fa-graduation-cap', 'color': '#74B9FF'},
        {'name': 'Lainnya', 'icon': 'fas fa-ellipsis-h', 'color': '#636E72'},
    ]
    for cat in income_categories:
        db.session.add(Category(name=cat['name'], type='income', icon=cat['icon'], color=cat['color'], user_id=user_id))
    for cat in expense_categories:
        db.session.add(Category(name=cat['name'], type='expense', icon=cat['icon'], color=cat['color'], user_id=user_id))
    db.session.commit()


def get_monthly_summary(user_id, month=None, year=None):
    """Dapatkan ringkasan keuangan bulanan."""
    today = date.today()
    if month is None:
        month = today.month
    if year is None:
        year = today.year

    start_date = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end_date = date(year, month, last_day)

    transactions = Transaction.query.filter(
        Transaction.user_id == user_id,
        Transaction.date >= start_date,
        Transaction.date <= end_date
    ).all()

    total_income = sum(t.amount for t in transactions if t.type == 'income')
    total_expense = sum(t.amount for t in transactions if t.type == 'expense')
    balance = total_income - total_expense

    return {
        'total_income': total_income,
        'total_expense': total_expense,
        'balance': balance,
        'month': month,
        'year': year,
        'transaction_count': len(transactions)
    }


# ─── Auth Routes ──────────────────────────────────────────────────────────────

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        errors = []
        if not username or len(username) < 3:
            errors.append('Username minimal 3 karakter.')
        if not email or '@' not in email:
            errors.append('Email tidak valid.')
        if not password or len(password) < 6:
            errors.append('Password minimal 6 karakter.')
        if password != confirm_password:
            errors.append('Konfirmasi password tidak cocok.')
        if User.query.filter_by(username=username).first():
            errors.append('Username sudah digunakan.')
        if User.query.filter_by(email=email).first():
            errors.append('Email sudah digunakan.')

        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('auth/register.html')

        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        # Create default categories
        create_default_categories(user.id)

        flash('Registrasi berhasil! Silakan login.', 'success')
        return redirect(url_for('login'))

    return render_template('auth/register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash(f'Selamat datang, {user.username}!', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Username atau password salah.', 'danger')

    return render_template('auth/login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Anda telah logout.', 'info')
    return redirect(url_for('login'))


# ─── Main Routes ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    today = date.today()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)

    summary = get_monthly_summary(current_user.id, month, year)

    # Recent transactions
    recent_transactions = Transaction.query.filter_by(
        user_id=current_user.id
    ).order_by(Transaction.date.desc(), Transaction.created_at.desc()).limit(10).all()

    # Savings goals
    savings_goals = SavingsGoal.query.filter_by(user_id=current_user.id).all()
    total_savings = sum(g.current_amount for g in savings_goals)

    # Income by category (for pie chart)
    income_by_category = db.session.query(
        Category.name, Category.color,
        db.func.sum(Transaction.amount).label('total')
    ).join(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'income',
        Transaction.date >= date(year, month, 1),
        Transaction.date <= date(year, month, calendar.monthrange(year, month)[1])
    ).group_by(Category.id).all()

    # Expense by category (for pie chart)
    expense_by_category = db.session.query(
        Category.name, Category.color,
        db.func.sum(Transaction.amount).label('total')
    ).join(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'expense',
        Transaction.date >= date(year, month, 1),
        Transaction.date <= date(year, month, calendar.monthrange(year, month)[1])
    ).group_by(Category.id).all()

    # Daily spending trend (for line chart)
    last_day = calendar.monthrange(year, month)[1]
    daily_income = {}
    daily_expense = {}
    for day in range(1, last_day + 1):
        d = date(year, month, day)
        daily_income[day] = 0
        daily_expense[day] = 0

    month_transactions = Transaction.query.filter(
        Transaction.user_id == current_user.id,
        Transaction.date >= date(year, month, 1),
        Transaction.date <= date(year, month, last_day)
    ).all()

    for t in month_transactions:
        if t.type == 'income':
            daily_income[t.date.day] = daily_income.get(t.date.day, 0) + t.amount
        else:
            daily_expense[t.date.day] = daily_expense.get(t.date.day, 0) + t.amount

    # Budgets
    budgets = Budget.query.filter_by(
        user_id=current_user.id, month=month, year=year
    ).all()
    budget_data = []
    for b in budgets:
        spent = sum(t.amount for t in Transaction.query.filter(
            Transaction.user_id == current_user.id,
            Transaction.type == 'expense',
            Transaction.category_id == b.category_id,
            Transaction.date >= date(year, month, 1),
            Transaction.date <= date(year, month, last_day)
        ).all())
        budget_data.append({
            'category': b.category.name,
            'color': b.category.color,
            'budget': b.amount,
            'spent': spent,
            'remaining': b.amount - spent,
            'percent': min((spent / b.amount * 100) if b.amount > 0 else 0, 100)
        })

    months_id = {
        1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
        5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
        9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
    }

    return render_template('dashboard.html',
                           summary=summary,
                           recent_transactions=recent_transactions,
                           savings_goals=savings_goals,
                           total_savings=total_savings,
                           income_by_category=json.dumps([
                               {'name': r[0], 'color': r[1], 'value': r[2]} for r in income_by_category
                           ]),
                           expense_by_category=json.dumps([
                               {'name': r[0], 'color': r[1], 'value': r[2]} for r in expense_by_category
                           ]),
                           daily_income=json.dumps(list(daily_income.values())),
                           daily_expense=json.dumps(list(daily_expense.values())),
                           daily_labels=json.dumps(list(range(1, last_day + 1))),
                           budget_data=budget_data,
                           month=month,
                           year=year,
                           months_id=months_id,
                           today=today)


# ─── Transaction Routes ──────────────────────────────────────────────────────

@app.route('/transactions')
@login_required
def transactions():
    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type', 'all')
    category_filter = request.args.get('category', 0, type=int)
    payment_method_filter = request.args.get('payment_method', 'all')
    date_filter = request.args.get('date', '')

    query = Transaction.query.filter_by(user_id=current_user.id)

    if type_filter in ('income', 'expense'):
        query = query.filter_by(type=type_filter)
    if category_filter > 0:
        query = query.filter_by(category_id=category_filter)
    if payment_method_filter in ('Tunai', 'M-Banking'):
        query = query.filter_by(payment_method=payment_method_filter)
    if date_filter:
        try:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter_by(date=filter_date)
        except ValueError:
            pass

    transactions = query.order_by(
        Transaction.date.desc(), Transaction.created_at.desc()
    ).paginate(page=page, per_page=15, error_out=False)

    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()

    return render_template('transactions.html',
                           transactions=transactions,
                           categories=categories,
                           type_filter=type_filter,
                           category_filter=category_filter,
                           payment_method_filter=payment_method_filter,
                           date_filter=date_filter)


@app.route('/transaction/add', methods=['GET', 'POST'])
@login_required
def add_transaction():
    if request.method == 'POST':
        trans_type = request.form.get('type', 'expense')
        amount = request.form.get('amount', 0, type=float)
        description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id', 0, type=int)
        trans_date = request.form.get('date', '')
        payment_method = request.form.get('payment_method', 'Tunai')

        if amount <= 0:
            flash('Jumlah harus lebih dari 0.', 'danger')
            return redirect(url_for('add_transaction'))

        try:
            trans_date = datetime.strptime(trans_date, '%Y-%m-%d').date()
        except ValueError:
            trans_date = date.today()

        transaction = Transaction(
            amount=amount,
            type=trans_type,
            description=description,
            category_id=category_id if category_id > 0 else None,
            date=trans_date,
            payment_method=payment_method,
            user_id=current_user.id
        )
        db.session.add(transaction)
        db.session.commit()

        type_label = 'Pemasukan' if trans_type == 'income' else 'Pengeluaran'
        flash(f'{type_label} berhasil ditambahkan!', 'success')
        return redirect(url_for('transactions'))

    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
    income_categories = [c for c in categories if c.type == 'income']
    expense_categories = [c for c in categories if c.type == 'expense']

    return render_template('add_transaction.html',
                           income_categories=income_categories,
                           expense_categories=expense_categories)


@app.route('/transaction/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_transaction(id):
    transaction = Transaction.query.filter_by(id=id, user_id=current_user.id).first_or_404()

    if request.method == 'POST':
        transaction.type = request.form.get('type', transaction.type)
        transaction.amount = request.form.get('amount', transaction.amount, type=float)
        transaction.description = request.form.get('description', '').strip()
        category_id = request.form.get('category_id', 0, type=int)
        transaction.category_id = category_id if category_id > 0 else None
        transaction.payment_method = request.form.get('payment_method', transaction.payment_method)

        try:
            transaction.date = datetime.strptime(request.form.get('date', ''), '%Y-%m-%d').date()
        except ValueError:
            pass

        db.session.commit()
        flash('Transaksi berhasil diperbarui!', 'success')
        return redirect(url_for('transactions'))

    categories = Category.query.filter_by(user_id=current_user.id).order_by(Category.name).all()
    income_categories = [c for c in categories if c.type == 'income']
    expense_categories = [c for c in categories if c.type == 'expense']

    return render_template('edit_transaction.html',
                           transaction=transaction,
                           income_categories=income_categories,
                           expense_categories=expense_categories)


@app.route('/transaction/delete/<int:id>', methods=['POST'])
@login_required
def delete_transaction(id):
    transaction = Transaction.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(transaction)
    db.session.commit()
    flash('Transaksi berhasil dihapus.', 'warning')
    return redirect(url_for('transactions'))


# ─── Savings Routes ──────────────────────────────────────────────────────────

@app.route('/savings')
@login_required
def savings():
    goals = SavingsGoal.query.filter_by(user_id=current_user.id).order_by(SavingsGoal.created_at.desc()).all()
    total_saved = sum(g.current_amount for g in goals)
    total_target = sum(g.target_amount for g in goals)
    return render_template('savings.html', goals=goals, total_saved=total_saved, total_target=total_target)


@app.route('/savings/add', methods=['GET', 'POST'])
@login_required
def add_savings_goal():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        target_amount = request.form.get('target_amount', 0, type=float)
        deadline = request.form.get('deadline', '')
        icon = request.form.get('icon', 'fas fa-piggy-bank')
        color = request.form.get('color', '#00B894')

        if not name:
            flash('Nama target harus diisi.', 'danger')
            return redirect(url_for('add_savings_goal'))

        if target_amount <= 0:
            flash('Target harus lebih dari 0.', 'danger')
            return redirect(url_for('add_savings_goal'))

        try:
            deadline = datetime.strptime(deadline, '%Y-%m-%d').date() if deadline else None
        except ValueError:
            deadline = None

        goal = SavingsGoal(
            name=name,
            target_amount=target_amount,
            deadline=deadline,
            icon=icon,
            color=color,
            user_id=current_user.id
        )
        db.session.add(goal)
        db.session.commit()

        flash(f'Target tabungan "{name}" berhasil dibuat!', 'success')
        return redirect(url_for('savings'))

    return render_template('add_savings.html')


@app.route('/savings/<int:id>')
@login_required
def savings_detail(id):
    goal = SavingsGoal.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    deposits = SavingsDeposit.query.filter_by(goal_id=goal.id).order_by(SavingsDeposit.date.desc()).all()
    return render_template('savings_detail.html', goal=goal, deposits=deposits)


@app.route('/savings/<int:id>/deposit', methods=['POST'])
@login_required
def add_deposit(id):
    goal = SavingsGoal.query.filter_by(id=id, user_id=current_user.id).first_or_404()

    amount = request.form.get('amount', 0, type=float)
    depositor_name = request.form.get('depositor_name', '').strip()
    note = request.form.get('note', '').strip()

    if amount <= 0:
        flash('Jumlah setoran harus lebih dari 0.', 'danger')
        return redirect(url_for('savings_detail', id=id))

    deposit = SavingsDeposit(
        amount=amount,
        depositor_name=depositor_name,
        note=note,
        goal_id=goal.id
    )
    goal.current_amount += amount

    db.session.add(deposit)
    db.session.commit()

    flash(f'Setoran Rp {amount:,.0f} berhasil ditambahkan!', 'success')
    return redirect(url_for('savings_detail', id=id))


@app.route('/savings/deposit/<int:id>/delete', methods=['POST'])
@login_required
def delete_deposit(id):
    deposit = SavingsDeposit.query.join(SavingsGoal).filter(
        SavingsDeposit.id == id,
        SavingsGoal.user_id == current_user.id
    ).first_or_404()
    
    goal = deposit.goal
    
    # Kurangi saldo deposit dari target tabungan
    goal.current_amount -= deposit.amount
    if goal.current_amount < 0:
        goal.current_amount = 0
        
    db.session.delete(deposit)
    db.session.commit()
    
    flash('Setoran berhasil dihapus.', 'warning')
    return redirect(url_for('savings_detail', id=goal.id))


@app.route('/savings/<int:id>/delete', methods=['POST'])
@login_required
def delete_savings_goal(id):
    goal = SavingsGoal.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(goal)
    db.session.commit()
    flash(f'Target tabungan "{goal.name}" berhasil dihapus.', 'warning')
    return redirect(url_for('savings'))


# ─── Budget Routes ────────────────────────────────────────────────────────────

@app.route('/budgets')
@login_required
def budgets():
    today = date.today()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)

    budget_list = Budget.query.filter_by(
        user_id=current_user.id, month=month, year=year
    ).all()

    last_day = calendar.monthrange(year, month)[1]
    budget_data = []
    total_budget = 0
    total_spent = 0

    for b in budget_list:
        spent = db.session.query(db.func.sum(Transaction.amount)).filter(
            Transaction.user_id == current_user.id,
            Transaction.type == 'expense',
            Transaction.category_id == b.category_id,
            Transaction.date >= date(year, month, 1),
            Transaction.date <= date(year, month, last_day)
        ).scalar() or 0

        total_budget += b.amount
        total_spent += spent

        budget_data.append({
            'id': b.id,
            'category': b.category.name,
            'category_id': b.category_id,
            'color': b.category.color,
            'icon': b.category.icon,
            'budget': b.amount,
            'spent': spent,
            'remaining': b.amount - spent,
            'percent': min((spent / b.amount * 100) if b.amount > 0 else 0, 100)
        })

    expense_categories = Category.query.filter_by(
        user_id=current_user.id, type='expense'
    ).order_by(Category.name).all()

    months_id = {
        1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
        5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
        9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember'
    }

    return render_template('budgets.html',
                           budget_data=budget_data,
                           expense_categories=expense_categories,
                           total_budget=total_budget,
                           total_spent=total_spent,
                           month=month,
                           year=year,
                           months_id=months_id)


@app.route('/budget/add', methods=['POST'])
@login_required
def add_budget():
    category_id = request.form.get('category_id', 0, type=int)
    amount = request.form.get('amount', 0, type=float)
    month = request.form.get('month', date.today().month, type=int)
    year = request.form.get('year', date.today().year, type=int)

    if category_id <= 0 or amount <= 0:
        flash('Data anggaran tidak valid.', 'danger')
        return redirect(url_for('budgets', month=month, year=year))

    existing = Budget.query.filter_by(
        user_id=current_user.id, category_id=category_id, month=month, year=year
    ).first()

    if existing:
        existing.amount = amount
        flash('Anggaran berhasil diperbarui!', 'success')
    else:
        budget = Budget(
            category_id=category_id,
            amount=amount,
            month=month,
            year=year,
            user_id=current_user.id
        )
        db.session.add(budget)
        flash('Anggaran berhasil ditambahkan!', 'success')

    db.session.commit()
    return redirect(url_for('budgets', month=month, year=year))


@app.route('/budget/delete/<int:id>', methods=['POST'])
@login_required
def delete_budget(id):
    budget = Budget.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    month, year = budget.month, budget.year
    db.session.delete(budget)
    db.session.commit()
    flash('Anggaran berhasil dihapus.', 'warning')
    return redirect(url_for('budgets', month=month, year=year))


# ─── Reports / Analytics Routes ──────────────────────────────────────────────

@app.route('/reports')
@login_required
def reports():
    today = date.today()
    year = request.args.get('year', today.year, type=int)

    # Monthly totals for the year
    monthly_data = []
    for m in range(1, 13):
        summary = get_monthly_summary(current_user.id, m, year)
        monthly_data.append(summary)

    # Category breakdown for the year
    income_breakdown = db.session.query(
        Category.name, Category.color, Category.icon,
        db.func.sum(Transaction.amount).label('total')
    ).join(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'income',
        Transaction.date >= date(year, 1, 1),
        Transaction.date <= date(year, 12, 31)
    ).group_by(Category.id).order_by(db.func.sum(Transaction.amount).desc()).all()

    expense_breakdown = db.session.query(
        Category.name, Category.color, Category.icon,
        db.func.sum(Transaction.amount).label('total')
    ).join(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'expense',
        Transaction.date >= date(year, 1, 1),
        Transaction.date <= date(year, 12, 31)
    ).group_by(Category.id).order_by(db.func.sum(Transaction.amount).desc()).all()

    yearly_income = sum(m['total_income'] for m in monthly_data)
    yearly_expense = sum(m['total_expense'] for m in monthly_data)

    months_id = {
        1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
        5: 'Mei', 6: 'Jun', 7: 'Jul', 8: 'Agu',
        9: 'Sep', 10: 'Okt', 11: 'Nov', 12: 'Des'
    }

    return render_template('reports.html',
                           monthly_data=json.dumps(monthly_data),
                           income_breakdown=json.dumps([
                               {'name': r[0], 'color': r[1], 'icon': r[2], 'value': r[3]}
                               for r in income_breakdown
                           ]),
                           expense_breakdown=json.dumps([
                               {'name': r[0], 'color': r[1], 'icon': r[2], 'value': r[3]}
                               for r in expense_breakdown
                           ]),
                           yearly_income=yearly_income,
                           yearly_expense=yearly_expense,
                           year=year,
                           months_id=months_id)


# ─── Category Management ─────────────────────────────────────────────────────

@app.route('/categories')
@login_required
def categories():
    income_cats = Category.query.filter_by(user_id=current_user.id, type='income').order_by(Category.name).all()
    expense_cats = Category.query.filter_by(user_id=current_user.id, type='expense').order_by(Category.name).all()
    return render_template('categories.html', income_categories=income_cats, expense_categories=expense_cats)


@app.route('/category/add', methods=['POST'])
@login_required
def add_category():
    name = request.form.get('name', '').strip()
    cat_type = request.form.get('type', 'expense')
    icon = request.form.get('icon', 'fas fa-tag')
    color = request.form.get('color', '#6C5CE7')

    if not name:
        flash('Nama kategori harus diisi.', 'danger')
        return redirect(url_for('categories'))

    category = Category(name=name, type=cat_type, icon=icon, color=color, user_id=current_user.id)
    db.session.add(category)
    db.session.commit()

    flash(f'Kategori "{name}" berhasil ditambahkan!', 'success')
    return redirect(url_for('categories'))


@app.route('/category/delete/<int:id>', methods=['POST'])
@login_required
def delete_category(id):
    category = Category.query.filter_by(id=id, user_id=current_user.id).first_or_404()
    db.session.delete(category)
    db.session.commit()
    flash(f'Kategori "{category.name}" berhasil dihapus.', 'warning')
    return redirect(url_for('categories'))


# ─── API Endpoints ────────────────────────────────────────────────────────────

@app.route('/api/chart-data')
@login_required
def chart_data():
    """Endpoint untuk data chart dinamis."""
    today = date.today()
    month = request.args.get('month', today.month, type=int)
    year = request.args.get('year', today.year, type=int)

    last_day = calendar.monthrange(year, month)[1]

    income_by_cat = db.session.query(
        Category.name, Category.color,
        db.func.sum(Transaction.amount).label('total')
    ).join(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'income',
        Transaction.date >= date(year, month, 1),
        Transaction.date <= date(year, month, last_day)
    ).group_by(Category.id).all()

    expense_by_cat = db.session.query(
        Category.name, Category.color,
        db.func.sum(Transaction.amount).label('total')
    ).join(Transaction).filter(
        Transaction.user_id == current_user.id,
        Transaction.type == 'expense',
        Transaction.date >= date(year, month, 1),
        Transaction.date <= date(year, month, last_day)
    ).group_by(Category.id).all()

    return jsonify({
        'income': [{'name': r[0], 'color': r[1], 'value': r[2]} for r in income_by_cat],
        'expense': [{'name': r[0], 'color': r[1], 'value': r[2]} for r in expense_by_cat]
    })


# ─── Database Initialization ─────────────────────────────────────────────────

with app.app_context():
    db.create_all()

# ─── Run ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True, port=5000)
