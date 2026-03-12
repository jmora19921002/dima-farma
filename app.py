from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, g, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_migrate import Migrate
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime, timedelta
import json
from config import Config
import click
import pymysql
from urllib.parse import urlparse

app = Flask(__name__)
app.config.from_object(Config)

from models import db

db.init_app(app)
migrate = Migrate(app, db)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'admin_login'
CORS(app)

from models import User, Pharmacy, Product, Order, OrderItem, Subscription, InventoryMovement, Category, AuditLog, Promotion

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

@app.before_request
def before_request():
    g.current_pharmacy = None
    
    if request.host.startswith('pharmacy-'):
        pharmacy_slug = request.host.split('.')[0].replace('pharmacy-', '')
        g.current_pharmacy = Pharmacy.query.filter_by(slug=pharmacy_slug, is_active=True).first()
    elif request.path.startswith('/pharmacy/'):
        pharmacy_slug = request.path.split('/')[2]
        g.current_pharmacy = Pharmacy.query.filter_by(slug=pharmacy_slug, is_active=True).first()

@app.route('/test-login')
def test_login():
    return render_template('admin/login_simple.html')

@app.route('/')
def admin_home():
    if not current_user.is_authenticated or current_user.role != 'server_admin':
        return redirect(url_for('admin_login'))
    
    total_pharmacies = Pharmacy.query.count()
    active_pharmacies = Pharmacy.query.filter_by(is_active=True).count()
    pending_subscriptions = Subscription.query.filter_by(status='pending').count()
    
    return render_template('admin/home.html',
                         total_pharmacies=total_pharmacies,
                         active_pharmacies=active_pharmacies,
                         pending_subscriptions=pending_subscriptions,
                         current_time=datetime.now())

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email, role='server_admin').first()
        
        if user:
            if check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for('admin_home'))
        
        flash('Credenciales inválidas', 'error')
    
    return render_template('admin/login.html')

@app.route('/admin/pharmacies', methods=['GET', 'POST'])
@login_required
def admin_pharmacies():
    if current_user.role != 'server_admin':
        flash('Acceso denegado', 'error')
        return redirect(url_for('admin_login'))
    
    if request.method == 'POST':
        try:
            name = request.form['name']
            slug = request.form['slug']
            description = request.form['description']
            address = request.form['address']
            phone = request.form['phone']
            email = request.form['email']
            theme_color = request.form['theme_color']
            
            # Manejo del Logo
            logo_url = None
            if 'logo' in request.files:
                file = request.files['logo']
                if file and file.filename != '':
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        filename = secure_filename(f"logo_{slug}_{file.filename}")
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        logo_url = f"/static/uploads/{filename}"
            
            # Verificar si el slug ya existe
            if Pharmacy.query.filter_by(slug=slug).first():
                flash(f'El slug "{slug}" ya está en uso. Por favor elige otro.', 'error')
                return redirect(url_for('admin_pharmacies'))
            
            # Crear un nuevo usuario administrador para la farmacia
            # Usamos el email de la farmacia para el admin, o uno por defecto
            admin_email = email if email else f"admin@{slug}.com"
            
            # Verificar si el email ya existe
            if User.query.filter_by(email=admin_email).first():
                flash(f'El email "{admin_email}" ya está registrado como usuario.', 'error')
                return redirect(url_for('admin_pharmacies'))
            
            admin_user = User(
                name=f"Admin {name}",
                email=admin_email,
                role='pharmacy_admin',
                is_active=True
            )
            admin_user.set_password('master') # Contraseña por defecto
            db.session.add(admin_user)
            db.session.flush() # Para obtener el ID del usuario
            
            new_pharmacy = Pharmacy(
                name=name,
                slug=slug,
                description=description,
                address=address,
                phone=phone,
                email=email,
                theme_color=theme_color,
                logo_url=logo_url,
                admin_user_id=admin_user.id
            )
            
            db.session.add(new_pharmacy)
            db.session.commit()
            
            flash(f'Farmacia "{name}" creada exitosamente. Usuario administrador: {admin_email} (clave: master)', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear la farmacia: {str(e)}', 'error')
        
        return redirect(url_for('admin_pharmacies'))
    
    pharmacies = Pharmacy.query.all()
    return render_template('admin/pharmacies.html', pharmacies=pharmacies)

@app.route('/admin/pharmacy/<int:pharmacy_id>/toggle')
@login_required
def toggle_pharmacy_status(pharmacy_id):
    if current_user.role != 'server_admin':
        flash('Acceso denegado', 'error')
        return redirect(url_for('admin_login'))
    
    pharmacy = Pharmacy.query.get_or_404(pharmacy_id)
    pharmacy.is_active = not pharmacy.is_active
    db.session.commit()
    
    status = 'activada' if pharmacy.is_active else 'desactivada'
    flash(f'Farmacia {status} exitosamente!', 'success')
    return redirect(url_for('admin_pharmacies'))

@app.route('/admin/pharmacy/<int:pharmacy_id>/edit', methods=['GET', 'POST'])
@login_required
def admin_edit_pharmacy(pharmacy_id):
    if current_user.role != 'server_admin':
        flash('Acceso denegado', 'error')
        return redirect(url_for('admin_login'))
    
    pharmacy = Pharmacy.query.get_or_404(pharmacy_id)
    
    if request.method == 'POST':
        try:
            name = request.form['name']
            slug = request.form['slug']
            description = request.form['description']
            address = request.form['address']
            phone = request.form['phone']
            email = request.form['email']
            theme_color = request.form['theme_color']
            
            # Verificar si el slug ya existe (en otra farmacia)
            existing_pharmacy = Pharmacy.query.filter_by(slug=slug).first()
            if existing_pharmacy and existing_pharmacy.id != pharmacy.id:
                flash(f'El slug "{slug}" ya está en uso por otra farmacia.', 'error')
                return redirect(url_for('admin_pharmacies'))
            
            # Manejo del Logo
            if 'logo' in request.files:
                file = request.files['logo']
                if file and file.filename != '':
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        # Eliminar logo anterior si existe
                        if pharmacy.logo_url:
                            old_filename = pharmacy.logo_url.split('/')[-1]
                            old_filepath = os.path.join(app.config['UPLOAD_FOLDER'], old_filename)
                            if os.path.exists(old_filepath):
                                try:
                                    os.remove(old_filepath)
                                except Exception as e:
                                    print(f"Error al eliminar logo anterior: {e}")
                        
                        filename = secure_filename(f"logo_{slug}_{file.filename}")
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        pharmacy.logo_url = f"/static/uploads/{filename}"
            
            # Actualizar datos de la farmacia
            pharmacy.name = name
            pharmacy.slug = slug
            pharmacy.description = description
            pharmacy.address = address
            pharmacy.phone = phone
            pharmacy.email = email
            pharmacy.theme_color = theme_color
            
            db.session.commit()
            flash(f'Farmacia "{name}" actualizada exitosamente.', 'success')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar la farmacia: {str(e)}', 'error')
        
        return redirect(url_for('admin_pharmacies'))
    
    return redirect(url_for('admin_pharmacies'))

@app.route('/admin/pharmacy/<int:pharmacy_id>/users')
@login_required
def admin_pharmacy_users(pharmacy_id):
    if current_user.role != 'server_admin':
        flash('Acceso denegado', 'error')
        return redirect(url_for('admin_login'))
    
    pharmacy = Pharmacy.query.get_or_404(pharmacy_id)
    # Buscamos usuarios que sean admin de esta farmacia o empleados (si hubiera)
    # En este modelo, el admin_user_id está en la farmacia, pero el usuario puede tener el rol pharmacy_admin
    # Vamos a buscar todos los usuarios cuyo pharmacy_id (si existiera en User) coincida, 
    # o simplemente el admin principal por ahora.
    
    # Nota: El modelo User tiene una relación 'pharmacy' que usa backref 'admin_user'.
    # Si queremos ver todos los usuarios vinculados, necesitamos filtrar por pharmacy_id si existiera.
    # Dado que el modelo User NO tiene pharmacy_id, pero Pharmacy tiene admin_user_id:
    users = [pharmacy.admin_user] if pharmacy.admin_user else []
    
    return render_template('admin/pharmacy_users.html', pharmacy=pharmacy, users=users)

@app.route('/admin/user/<int:user_id>/reset_password')
@login_required
def admin_reset_user_password(user_id):
    if current_user.role != 'server_admin':
        flash('Acceso denegado', 'error')
        return redirect(url_for('admin_login'))
    
    user = User.query.get_or_404(user_id)
    user.set_password('master')
    db.session.commit()
    
    flash(f'Contraseña de {user.email} restablecida a "master"', 'success')
    
    # Redirigir de vuelta a la página de usuarios de su farmacia si es admin de alguna
    if user.pharmacy:
        return redirect(url_for('admin_pharmacy_users', pharmacy_id=user.pharmacy.id))
    return redirect(url_for('admin_pharmacies'))

@app.route('/admin/subscriptions')
@login_required
def admin_subscriptions():
    if current_user.role != 'server_admin':
        flash('Acceso denegado', 'error')
        return redirect(url_for('admin_login'))
    
    subscriptions = Subscription.query.all()
    return render_template('admin/subscriptions.html', subscriptions=subscriptions)

@app.route('/pharmacy/<slug>/register', methods=['GET', 'POST'])
def pharmacy_register(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    if current_user.is_authenticated:
        return redirect(url_for('pharmacy_home', slug=slug))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        phone = request.form.get('phone')
        address = request.form.get('address')
        
        if User.query.filter_by(email=email).first():
            flash('El correo electrónico ya está registrado', 'error')
            return redirect(url_for('pharmacy_register', slug=slug))
        
        user = User(
            name=name,
            email=email,
            role='customer',
            phone=phone,
            address=address
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        flash('Registro exitoso. ¡Bienvenido!', 'success')
        return redirect(url_for('pharmacy_home', slug=slug))
    
    return render_template('pharmacy/register.html', pharmacy=pharmacy)

@app.route('/pharmacy/<slug>/login', methods=['GET', 'POST'])
def pharmacy_login(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    if current_user.is_authenticated:
        return redirect(url_for('pharmacy_home', slug=slug))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            # Update last login
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            flash('Sesión iniciada correctamente', 'success')
            return redirect(url_for('pharmacy_home', slug=slug))
        else:
            flash('Credenciales inválidas', 'error')
    
    return render_template('pharmacy/login.html', pharmacy=pharmacy)

@app.route('/pharmacy/<slug>')
def pharmacy_home(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    products = Product.query.filter_by(pharmacy_id=pharmacy.id, is_active=True).all()
    
    now = datetime.utcnow()
    promotions = Promotion.query.filter(
        Promotion.pharmacy_id == pharmacy.id,
        Promotion.is_active == True,
        (Promotion.start_date == None) | (Promotion.start_date <= now),
        (Promotion.end_date == None) | (Promotion.end_date >= now)
    ).order_by(Promotion.display_order).all()
    
    return render_template('pharmacy/home.html', pharmacy=pharmacy, products=products, promotions=promotions)

@app.route('/pharmacy/<slug>/products')
def pharmacy_products(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    max_price = request.args.get('max_price', '').strip()
    
    query = Product.query.filter_by(pharmacy_id=pharmacy.id, is_active=True)
    
    if search_query:
        query = query.filter(Product.name.ilike(f'%{search_query}%'))
    
    if category_filter:
        query = query.filter(Product.category == category_filter)
    
    if max_price:
        try:
            query = query.filter(Product.price <= float(max_price))
        except ValueError:
            pass
    
    pagination = query.paginate(page=page, per_page=50, error_out=False)
    products = pagination.items
    
    return render_template('pharmacy/products.html', 
                         pharmacy=pharmacy, 
                         products=products,
                         pagination=pagination,
                         search_query=search_query,
                         category_filter=category_filter,
                         max_price=max_price)

@app.route('/pharmacy/<slug>/product/<int:product_id>')
def pharmacy_product_detail(slug, product_id):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    product = Product.query.filter_by(id=product_id, pharmacy_id=pharmacy.id, is_active=True).first_or_404()
    
    return render_template('pharmacy/product_detail.html', pharmacy=pharmacy, product=product)

@app.route('/pharmacy/<slug>/cart')
def pharmacy_cart(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    cart_items = []
    total = 0
    
    if 'cart' in session:
        for product_id, quantity in session['cart'].items():
            product = Product.query.get(product_id)
            if product and product.pharmacy_id == pharmacy.id:
                cart_items.append({
                    'product': product,
                    'quantity': quantity,
                    'subtotal': product.price * quantity
                })
                total += product.price * quantity
    
    return render_template('pharmacy/cart.html', pharmacy=pharmacy, cart_items=cart_items, total=total)

@app.route('/pharmacy/<slug>/add_to_cart', methods=['POST'])
def pharmacy_add_to_cart(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    data = request.get_json()
    product_id = data.get('product_id')
    quantity = data.get('quantity', 1)
    
    product = Product.query.filter_by(id=product_id, pharmacy_id=pharmacy.id, is_active=True).first()
    if not product:
        return jsonify({'success': False, 'error': 'Producto no encontrado'})
    
    if 'cart' not in session:
        session['cart'] = {}
    
    if str(product_id) in session['cart']:
        session['cart'][str(product_id)] += quantity
    else:
        session['cart'][str(product_id)] = quantity
    
    session.modified = True
    return jsonify({'success': True, 'cart_count': len(session['cart'])})

@app.route('/pharmacy/<slug>/checkout', methods=['GET', 'POST'])
def pharmacy_checkout(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    if request.method == 'POST':
        data = request.form
        
        import uuid
        order_number = f"{pharmacy.slug.upper()}-{uuid.uuid4().hex[:8].upper()}"
        
        order = Order(
            order_number=order_number,
            customer_name=data['customer_name'],
            customer_email=data['customer_email'],
            customer_phone=data['customer_phone'],
            customer_address=data['customer_address'],
            total_amount=float(data['total_amount']),
            status='pending',
            payment_status='pending',
            pharmacy_id=pharmacy.id,
            user_id=current_user.id if current_user.is_authenticated else None
        )
        
        db.session.add(order)
        db.session.commit()
        
        for product_id, quantity in session['cart'].items():
            product = Product.query.get(product_id)
            if product and product.pharmacy_id == pharmacy.id:
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product_id,
                    quantity=quantity,
                    price=product.price
                )
                db.session.add(order_item)
        
        db.session.commit()
        
        session.pop('cart', None)
        flash('Pedido realizado exitosamente!', 'success')
        return redirect(url_for('pharmacy_order_confirmation', slug=slug, order_id=order.id))
    
    cart_items = []
    total = 0
    
    if 'cart' in session:
        for product_id, quantity in session['cart'].items():
            product = Product.query.get(product_id)
            if product and product.pharmacy_id == pharmacy.id:
                cart_items.append({
                    'product': product,
                    'quantity': quantity,
                    'subtotal': product.price * quantity
                })
                total += product.price * quantity
    
    return render_template('pharmacy/checkout.html', pharmacy=pharmacy, cart_items=cart_items, total=total)

@app.route('/pharmacy/<slug>/order/<int:order_id>/confirmation')
def pharmacy_order_confirmation(slug, order_id):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    order = Order.query.filter_by(id=order_id, pharmacy_id=pharmacy.id).first_or_404()
    
    return render_template('pharmacy/order_confirmation.html', pharmacy=pharmacy, order=order)

@app.route('/pharmacy/<slug>/admin/login', methods=['GET', 'POST'])
def pharmacy_admin_login(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        user = User.query.filter_by(email=email, role='pharmacy_admin').first()
        if user and user.pharmacy and user.pharmacy.slug == slug:
            if check_password_hash(user.password_hash, password):
                login_user(user)
                return redirect(url_for('pharmacy_admin_dashboard', slug=slug))
        
        flash('Credenciales inválidas', 'error')
    
    return render_template('pharmacy/admin/login.html', pharmacy=pharmacy)

@app.route('/pharmacy/<slug>/admin/dashboard')
@login_required
def pharmacy_admin_dashboard(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    if current_user.role != 'pharmacy_admin' or not current_user.pharmacy or current_user.pharmacy.slug != slug:
        flash('Acceso denegado', 'error')
        return redirect(url_for('pharmacy_admin_login', slug=slug))
    
    total_products = Product.query.filter_by(pharmacy_id=pharmacy.id).count()
    total_orders = Order.query.filter_by(pharmacy_id=pharmacy.id).count()
    recent_orders = Order.query.filter_by(pharmacy_id=pharmacy.id).order_by(Order.created_at.desc()).limit(5).all()
    
    return render_template('pharmacy/admin/dashboard.html', 
                         pharmacy=pharmacy, 
                         total_products=total_products,
                         total_orders=total_orders,
                         recent_orders=recent_orders)

@app.route('/pharmacy/<slug>/admin/products')
@login_required
def pharmacy_admin_products(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    if current_user.role != 'pharmacy_admin' or not current_user.pharmacy or current_user.pharmacy.slug != slug:
        flash('Acceso denegado', 'error')
        return redirect(url_for('pharmacy_admin_login', slug=slug))
    
    products = Product.query.filter_by(pharmacy_id=pharmacy.id).all()
    return render_template('pharmacy/admin/products.html', pharmacy=pharmacy, products=products)

@app.route('/pharmacy/<slug>/admin/orders')
@login_required
def pharmacy_admin_orders(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    if current_user.role != 'pharmacy_admin' or not current_user.pharmacy or current_user.pharmacy.slug != slug:
        flash('Acceso denegado', 'error')
        return redirect(url_for('pharmacy_admin_login', slug=slug))
    
    orders = Order.query.filter_by(pharmacy_id=pharmacy.id).order_by(Order.created_at.desc()).all()
    return render_template('pharmacy/admin/orders.html', pharmacy=pharmacy, orders=orders)

@app.route('/pharmacy/<slug>/admin/products/add', methods=['GET', 'POST'])
@login_required
def pharmacy_admin_add_product(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    if current_user.role != 'pharmacy_admin' or not current_user.pharmacy or current_user.pharmacy.slug != slug:
        flash('Acceso denegado', 'error')
        return redirect(url_for('pharmacy_admin_login', slug=slug))
    
    if request.method == 'POST':
        try:
            name = request.form['name']
            description = request.form['description']
            price = float(request.form['price'])
            stock_quantity = int(request.form['stock_quantity'])
            category = request.form['category']
            sku = request.form['sku']
            
            image_url = None
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename != '':
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        filename = secure_filename(f"{pharmacy.slug}_{sku}_{file.filename}")
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        
                        file.save(filepath)
                        image_url = f"/static/uploads/{filename}"
            
            product = Product(
                name=name,
                description=description,
                price=price,
                stock_quantity=stock_quantity,
                category=category,
                sku=sku,
                image_url=image_url,
                pharmacy_id=pharmacy.id
            )
            
            db.session.add(product)
            db.session.commit()
            
            flash('Producto agregado exitosamente!', 'success')
            return redirect(url_for('pharmacy_admin_products', slug=slug))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al agregar producto: {str(e)}', 'error')
    
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('pharmacy/admin/add_product.html', pharmacy=pharmacy, categories=categories)

@app.route('/pharmacy/<slug>/admin/products/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
def pharmacy_admin_edit_product(slug, product_id):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    product = Product.query.filter_by(id=product_id, pharmacy_id=pharmacy.id).first_or_404()
    
    if current_user.role != 'pharmacy_admin' or not current_user.pharmacy or current_user.pharmacy.slug != slug:
        flash('Acceso denegado', 'error')
        return redirect(url_for('pharmacy_admin_login', slug=slug))
    
    if request.method == 'POST':
        try:
            product.name = request.form['name']
            product.description = request.form['description']
            product.price = float(request.form['price'])
            product.stock_quantity = int(request.form['stock_quantity'])
            product.category = request.form['category']
            product.sku = request.form['sku']
            
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename != '':
                    allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                    if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                        if product.image_url:
                            old_filepath = os.path.join(app.root_path, 'static', product.image_url.lstrip('/'))
                            if os.path.exists(old_filepath):
                                os.remove(old_filepath)
                        
                        filename = secure_filename(f"{pharmacy.slug}_{product.sku}_{file.filename}")
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        product.image_url = f"/static/uploads/{filename}"
            
            db.session.commit()
            flash('Producto actualizado exitosamente!', 'success')
            return redirect(url_for('pharmacy_admin_products', slug=slug))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar producto: {str(e)}', 'error')
    
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('pharmacy/admin/edit_product.html', pharmacy=pharmacy, product=product, categories=categories)

@app.route('/pharmacy/<slug>/admin/products/<int:product_id>/delete', methods=['POST'])
@login_required
def pharmacy_admin_delete_product(slug, product_id):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    product = Product.query.filter_by(id=product_id, pharmacy_id=pharmacy.id).first_or_404()
    
    if current_user.role != 'pharmacy_admin' or not current_user.pharmacy or current_user.pharmacy.slug != slug:
        flash('Acceso denegado', 'error')
        return redirect(url_for('pharmacy_admin_login', slug=slug))
    
    try:
        if product.image_url:
            filepath = os.path.join(app.root_path, 'static', product.image_url.lstrip('/'))
            if os.path.exists(filepath):
                os.remove(filepath)
        
        db.session.delete(product)
        db.session.commit()
        flash('Producto eliminado exitosamente!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar producto: {str(e)}', 'error')
    
    return redirect(url_for('pharmacy_admin_products', slug=slug))

@app.route('/pharmacy/<slug>/admin/promotions')
@login_required
def pharmacy_admin_promotions(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    if current_user.role != 'pharmacy_admin' or not current_user.pharmacy or current_user.pharmacy.slug != slug:
        flash('Acceso denegado', 'error')
        return redirect(url_for('pharmacy_admin_login', slug=slug))
    
    promotions = Promotion.query.filter_by(pharmacy_id=pharmacy.id).order_by(Promotion.display_order).all()
    products = Product.query.filter_by(pharmacy_id=pharmacy.id).all()
    return render_template('pharmacy/admin/promotions.html', pharmacy=pharmacy, promotions=promotions, products=products)

@app.route('/pharmacy/<slug>/admin/promotions/add', methods=['GET', 'POST'])
@login_required
def pharmacy_admin_add_promotion(slug):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    
    if current_user.role != 'pharmacy_admin' or not current_user.pharmacy or current_user.pharmacy.slug != slug:
        flash('Acceso denegado', 'error')
        return redirect(url_for('pharmacy_admin_login', slug=slug))
    
    if request.method == 'POST':
        try:
            title = request.form['title']
            description = request.form['description']
            promotion_type = request.form['promotion_type']
            link_url = request.form.get('link_url', '')
            discount_percentage = float(request.form.get('discount_percentage', 0))
            product_id = request.form.get('product_id')
            category = request.form.get('category')
            display_order = int(request.form.get('display_order', 0))
            is_active = 'is_active' in request.form
            
            start_date = None
            if request.form.get('start_date'):
                start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
            
            end_date = None
            if request.form.get('end_date'):
                end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
            
            image_url = None
            if promotion_type == 'image':
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename != '':
                        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                        if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                            filename = secure_filename(f"promo_{pharmacy.slug}_{int(datetime.now().timestamp())}_{file.filename}")
                            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                            file.save(filepath)
                            image_url = f"/static/uploads/{filename}"
            
            promotion = Promotion(
                title=title,
                description=description,
                image_url=image_url,
                link_url=link_url,
                promotion_type=promotion_type,
                discount_percentage=discount_percentage,
                product_id=product_id if product_id else None,
                category=category if category else None,
                display_order=display_order,
                is_active=is_active,
                start_date=start_date,
                end_date=end_date,
                pharmacy_id=pharmacy.id
            )
            
            db.session.add(promotion)
            db.session.commit()
            
            flash('Promoción creada exitosamente!', 'success')
            return redirect(url_for('pharmacy_admin_promotions', slug=slug))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al crear promoción: {str(e)}', 'error')
    
    products = Product.query.filter_by(pharmacy_id=pharmacy.id).all()
    return render_template('pharmacy/admin/add_promotion.html', pharmacy=pharmacy, products=products)

@app.route('/pharmacy/<slug>/admin/promotions/<int:promotion_id>/edit', methods=['GET', 'POST'])
@login_required
def pharmacy_admin_edit_promotion(slug, promotion_id):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    promotion = Promotion.query.filter_by(id=promotion_id, pharmacy_id=pharmacy.id).first_or_404()
    
    if current_user.role != 'pharmacy_admin' or not current_user.pharmacy or current_user.pharmacy.slug != slug:
        flash('Acceso denegado', 'error')
        return redirect(url_for('pharmacy_admin_login', slug=slug))
    
    if request.method == 'POST':
        try:
            promotion.title = request.form['title']
            promotion.description = request.form['description']
            promotion.promotion_type = request.form['promotion_type']
            promotion.link_url = request.form.get('link_url', '')
            promotion.discount_percentage = float(request.form.get('discount_percentage', 0))
            promotion.product_id = request.form.get('product_id') if request.form.get('product_id') else None
            promotion.category = request.form.get('category') if request.form.get('category') else None
            promotion.display_order = int(request.form.get('display_order', 0))
            promotion.is_active = 'is_active' in request.form
            
            if request.form.get('start_date'):
                promotion.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d')
            else:
                promotion.start_date = None
            
            if request.form.get('end_date'):
                promotion.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d')
            else:
                promotion.end_date = None
            
            if promotion.promotion_type == 'image':
                if 'image' in request.files:
                    file = request.files['image']
                    if file and file.filename != '':
                        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
                        if '.' in file.filename and file.filename.rsplit('.', 1)[1].lower() in allowed_extensions:
                            if promotion.image_url:
                                old_filepath = os.path.join(app.root_path, 'static', promotion.image_url.lstrip('/'))
                                if os.path.exists(old_filepath):
                                    os.remove(old_filepath)
                            
                            filename = secure_filename(f"promo_{pharmacy.slug}_{int(datetime.now().timestamp())}_{file.filename}")
                            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                            file.save(filepath)
                            promotion.image_url = f"/static/uploads/{filename}"
            
            db.session.commit()
            flash('Promoción actualizada exitosamente!', 'success')
            return redirect(url_for('pharmacy_admin_promotions', slug=slug))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar promoción: {str(e)}', 'error')
    
    products = Product.query.filter_by(pharmacy_id=pharmacy.id).all()
    return render_template('pharmacy/admin/edit_promotion.html', pharmacy=pharmacy, promotion=promotion, products=products)

@app.route('/pharmacy/<slug>/admin/promotions/<int:promotion_id>/delete', methods=['POST'])
@login_required
def pharmacy_admin_delete_promotion(slug, promotion_id):
    pharmacy = Pharmacy.query.filter_by(slug=slug, is_active=True).first_or_404()
    promotion = Promotion.query.filter_by(id=promotion_id, pharmacy_id=pharmacy.id).first_or_404()
    
    if current_user.role != 'pharmacy_admin' or not current_user.pharmacy or current_user.pharmacy.slug != slug:
        flash('Acceso denegado', 'error')
        return redirect(url_for('pharmacy_admin_login', slug=slug))
    
    try:
        if promotion.image_url:
            filepath = os.path.join(app.root_path, 'static', promotion.image_url.lstrip('/'))
            if os.path.exists(filepath):
                os.remove(filepath)
        
        db.session.delete(promotion)
        db.session.commit()
        flash('Promoción eliminada exitosamente!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar promoción: {str(e)}', 'error')
    
    return redirect(url_for('pharmacy_admin_promotions', slug=slug))

@app.route('/static/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('static/uploads', filename)

@app.route('/logout')
@app.route('/pharmacy/<slug>/logout')
@login_required
def logout(slug=None):
    logout_user()
    if slug:
        return redirect(url_for('pharmacy_home', slug=slug))
    return redirect(url_for('admin_home'))

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

@app.cli.command('create-admin')
@click.argument('name')
@click.argument('email')
@click.argument('password')
def create_admin(name, email, password):
    """Crea un usuario administrador del sistema."""
    if User.query.filter_by(email=email).first():
        print('Ya existe un usuario con ese email.')
        return
    admin = User(name=name, email=email, role='server_admin', is_active=True)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()
    print(f'Usuario administrador creado: {email}')

@app.cli.command('reset-passwords')
def reset_passwords():
    """Establece la contraseña de TODOS los usuarios a 'master'."""
    users = User.query.all()
    if not users:
        print('No hay usuarios registrados.')
        return
    
    confirm = click.confirm(f'¿Estás seguro de que quieres restablecer la contraseña de {len(users)} usuarios a "master"?', abort=True)
    
    for user in users:
        user.set_password('master')
    
    db.session.commit()
    print('✅ Todas las contraseñas han sido restablecidas a "master".')

if __name__ == '__main__':
    try:
        with app.app_context():
            db.create_all()
        print("✅ Base de datos creada exitosamente!")
    except Exception as e:
        print(f"⚠️  Error al conectar con la base de datos: {e}")
        print("💡 Asegúrate de que MySQL esté ejecutándose y las credenciales sean correctas")
    
    print("🚀 Iniciando aplicación Flask...")
    app.run(host='0.0.0.0', port=5000, debug=True)