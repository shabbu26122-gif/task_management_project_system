from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from bson.objectid import ObjectId
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this in production

# MongoDB connection
client = MongoClient('mongodb://localhost:27017/')
db = client['task_management']
users_collection = db['users']
tasks_collection = db['tasks']

# Initialize default admin user if doesn't exist
def init_admin():
    admin = users_collection.find_one({'role': 'admin'})
    if not admin:
        admin_user = {
            'username': 'admin',
            'email': 'admin@company.com',
            'password': generate_password_hash('admin123'),
            'role': 'admin',
            'full_name': 'System Administrator',
            'created_at': datetime.now()
        }
        users_collection.insert_one(admin_user)

init_admin()

@app.route('/')
def index():
    if 'user_id' in session:
        if session['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('employee_dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = users_collection.find_one({'username': username})
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = str(user['_id'])
            session['username'] = user['username']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            
            if user['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('employee_dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    # Get filter parameters
    status_filter = request.args.get('status', 'all')
    employee_filter = request.args.get('employee', 'all')
    
    # Build query
    query = {}
    if status_filter != 'all':
        query['status'] = status_filter
    if employee_filter != 'all':
        query['assigned_to'] = employee_filter
    
    tasks = list(tasks_collection.find(query).sort('created_at', -1))
    employees = list(users_collection.find({'role': 'employee'}))
    
    # Get task statistics
    total_tasks = tasks_collection.count_documents({})
    completed_tasks = tasks_collection.count_documents({'status': 'completed'})
    in_progress_tasks = tasks_collection.count_documents({'status': 'in_progress'})
    review_tasks = tasks_collection.count_documents({'status': 'review'})
    
    return render_template('admin_dashboard.html', 
                         tasks=tasks, 
                         employees=employees,
                         stats={
                             'total': total_tasks,
                             'completed': completed_tasks,
                             'in_progress': in_progress_tasks,
                             'review': review_tasks
                         },
                         current_status=status_filter,
                         current_employee=employee_filter)

@app.route('/employee/dashboard')
def employee_dashboard():
    if 'user_id' not in session or session['role'] != 'employee':
        return redirect(url_for('login'))
    
    status_filter = request.args.get('status', 'all')
    
    query = {'assigned_to': session['username']}
    if status_filter != 'all':
        query['status'] = status_filter
    
    tasks = list(tasks_collection.find(query).sort('created_at', -1))
    
    # Get task statistics for employee
    total_tasks = tasks_collection.count_documents({'assigned_to': session['username']})
    completed_tasks = tasks_collection.count_documents({'assigned_to': session['username'], 'status': 'completed'})
    in_progress_tasks = tasks_collection.count_documents({'assigned_to': session['username'], 'status': 'in_progress'})
    review_tasks = tasks_collection.count_documents({'assigned_to': session['username'], 'status': 'review'})
    
    return render_template('employee_dashboard.html', 
                         tasks=tasks,
                         stats={
                             'total': total_tasks,
                             'completed': completed_tasks,
                             'in_progress': in_progress_tasks,
                             'review': review_tasks
                         },
                         current_status=status_filter)

@app.route('/admin/employees')
def manage_employees():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    employees = list(users_collection.find({'role': 'employee'}))
    return render_template('manage_employees.html', employees=employees)

@app.route('/admin/add_employee', methods=['POST'])
def add_employee():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    username = request.form['username']
    email = request.form['email']
    full_name = request.form['full_name']
    password = request.form['password']
    
    # Check if username already exists
    if users_collection.find_one({'username': username}):
        flash('Username already exists', 'error')
        return redirect(url_for('manage_employees'))
    
    employee = {
        'username': username,
        'email': email,
        'full_name': full_name,
        'password': generate_password_hash(password),
        'role': 'employee',
        'created_at': datetime.now()
    }
    
    users_collection.insert_one(employee)
    flash('Employee added successfully', 'success')
    return redirect(url_for('manage_employees'))

@app.route('/admin/add_task', methods=['GET', 'POST'])
def add_task():
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        task = {
            'title': request.form['title'],
            'description': request.form['description'],
            'assigned_to': request.form['assigned_to'],
            'priority': request.form['priority'],
            'due_date': request.form['due_date'],
            'status': 'assigned',
            'created_by': session['username'],
            'created_at': datetime.now(),
            'comments': []
        }
        
        tasks_collection.insert_one(task)
        flash('Task assigned successfully', 'success')
        return redirect(url_for('admin_dashboard'))
    
    employees = list(users_collection.find({'role': 'employee'}))
    return render_template('add_task.html', employees=employees)

@app.route('/task/<task_id>')
def task_detail(task_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    task = tasks_collection.find_one({'_id': ObjectId(task_id)})
    if not task:
        flash('Task not found', 'error')
        return redirect(url_for('admin_dashboard' if session['role'] == 'admin' else 'employee_dashboard'))
    
    return render_template('task_detail.html', task=task)

@app.route('/update_task_status', methods=['POST'])
def update_task_status():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    task_id = request.form['task_id']
    new_status = request.form['status']
    
    tasks_collection.update_one(
        {'_id': ObjectId(task_id)},
        {'$set': {'status': new_status, 'updated_at': datetime.now()}}
    )
    
    flash('Task status updated successfully', 'success')
    return redirect(url_for('task_detail', task_id=task_id))

@app.route('/add_comment', methods=['POST'])
def add_comment():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    task_id = request.form['task_id']
    comment_text = request.form['comment']
    
    comment = {
        'text': comment_text,
        'author': session['full_name'],
        'username': session['username'],
        'timestamp': datetime.now()
    }
    
    tasks_collection.update_one(
        {'_id': ObjectId(task_id)},
        {'$push': {'comments': comment}}
    )
    
    flash('Comment added successfully', 'success')
    return redirect(url_for('task_detail', task_id=task_id))

@app.route('/delete_employee/<employee_id>')
def delete_employee(employee_id):
    if 'user_id' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    
    users_collection.delete_one({'_id': ObjectId(employee_id)})
    flash('Employee deleted successfully', 'success')
    return redirect(url_for('manage_employees'))

if __name__ == '__main__':
    app.run(debug=True)