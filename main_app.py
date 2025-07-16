from datetime import datetime, timedelta, date
import os
import mysql.connector
import logging
from flask import Flask, request, redirect, url_for, render_template, jsonify, flash
from werkzeug.utils import secure_filename
from flask import Blueprint
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# --- Main Flask App Initialization ---
app = Flask(__name__,
            template_folder='html', 
            static_folder='static')

# --- Configuration ---
app.secret_key = 'your-super-secret-key'
app.config['UPLOAD_FOLDER'] = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx'}

# --- Database Configuration ---
DB_HOST = "127.0.0.1"
DB_USER = "root"
DB_PASSWORD = "Divy@2308"
DB_NAME = "user_master"

# Configure basic logging
logging.basicConfig(level=logging.INFO)
def roles_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.user_type not in roles:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('tickets.dashboard'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- Helper Functions ---

def get_db_connection():
    """Establishes a connection to the MySQL database."""
    try:
        conn = mysql.connector.connect(
            host=DB_HOST,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME
        )
        return conn
    except mysql.connector.Error as err:
        app.logger.error(f"Error connecting to MySQL: {err}")
        return None

def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Blueprint for User Management ---
users_bp = Blueprint('users', __name__, template_folder='html')

# User management (Admin only)
@users_bp.route('/')
@login_required
@roles_required('Admin')
def index():
    """Serves the user form for new user creation, fetching managers."""
    conn = get_db_connection()
    managers = [] # Initialize an empty list for managers

    if not conn:
        flash('Database connection failed. Cannot fetch manager data.', 'error')
        # If DB connection fails, render with default values
        return render_template('user_form.html', managers=managers)

    cursor = conn.cursor(dictionary=True) # Use dictionary=True for easier access to column names
    try:
        # Fetch users with position 'Manager' or 'Senior'
        cursor.execute("SELECT id, name FROM users WHERE position IN ('Manager', 'Senior') ORDER BY name")
        managers = cursor.fetchall()
    except mysql.connector.Error as err:
        app.logger.error(f"Database Error fetching managers in index route: {err}")
        flash('Could not fetch manager data from the database.', 'error')
    finally:
        cursor.close()
        conn.close()

    # Pass the managers list to the template
    return render_template('user_form.html', managers=managers)

@users_bp.route('/users/', methods=['GET'])
@login_required
@roles_required('Admin')
def view_users():
    """Fetches all users from the database and displays them in a table."""
    conn = get_db_connection()
    if conn is None:
        return "Database connection failed! Please check server logs.", 500

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id,user_type, name, mobile, office_email, user_name, position, joining_date, status FROM users")
        users = cursor.fetchall()
        return render_template('user_data.html', users=users)
    except mysql.connector.Error as err:
        app.logger.error(f"Failed to fetch users. Error: {err}")
        return "Failed to fetch users.", 500
    finally:
        cursor.close()
        conn.close()
    
@users_bp.route('/submit_user', methods=['POST'])
def submit_user():
    """Handles the form submission and inserts data into the database."""
    if request.method == 'POST':
        # Extract data safely using .get() which returns None if the key is missing
        user_data = {
            'user_type': request.form.get('user_type'),
            'user_name': request.form.get('user_name'),
            'password': generate_password_hash(request.form.get('password')),
            'consultant_type': request.form.get('consultant_type'),
            'reporting_manager': request.form.get('reporting_manager'),
            'alternate_mobile': request.form.get('alternate_mobile'),
            'worksnap_credentials': request.form.get('worksnap_credentials'),
            'status': request.form.get('status'),
            'timesheet_notification': request.form.get('timesheet_notification'),
            'name': request.form.get('name'),
            'mobile': request.form.get('mobile'),
            'office_email': request.form.get('office_email'),
            'joining_date': request.form.get('joining_date') or None,
            'position': request.form.get('position'),
            'date_of_birth': request.form.get('date_of_birth') or None,
            'anniversary_date': request.form.get('anniversary_date') or None,
            'sap_server_credentials': request.form.get('sap_server_credentials'),
            'allow_backdated_timesheet': request.form.get('allow_backdated_timesheet')
        }

        conn = get_db_connection()
        if conn is None:
            flash("Database connection failed! Please check server logs.", 'danger')
            return redirect(url_for('users.index'))

        cursor = conn.cursor()
        sql = """
        INSERT INTO users (
            user_type, user_name, password, consultant_type, reporting_manager,
            alternate_mobile, worksnap_credentials, status, timesheet_notification,
            name, mobile, office_email, joining_date, position, date_of_birth,
            anniversary_date, sap_server_credentials, allow_backdated_timesheet
        ) VALUES (
            %(user_type)s, %(user_name)s, %(password)s, %(consultant_type)s, %(reporting_manager)s,
            %(alternate_mobile)s, %(worksnap_credentials)s, %(status)s, %(timesheet_notification)s,
            %(name)s, %(mobile)s, %(office_email)s, %(joining_date)s, %(position)s, %(date_of_birth)s,
            %(anniversary_date)s, %(sap_server_credentials)s, %(allow_backdated_timesheet)s
        )
        """
        try:
            cursor.execute(sql, user_data)
            conn.commit()
            flash(f"User '{user_data.get('name')}' was added successfully!", 'success')
            return redirect(url_for('users.view_users'))
        except mysql.connector.Error as err:
            conn.rollback()
            app.logger.error(f"Failed to add user. Error: {err}")
            error_message = "Failed to add user. User Name or Office Email already exists."
            if err.errno == 1062:
                error_message = "Failed to add user. User Name or Office Email already exists."
            flash(error_message, 'danger')
            return redirect(url_for('users.index'))
        finally:
            cursor.close()
            conn.close()

    return redirect(url_for('users.index'))

@users_bp.route('/edit_user/<int:user_id>')
def edit_user(user_id):
    """Fetches a single user's data and managers, then renders the form for editing."""
    conn = get_db_connection()
    user = None
    managers = []

    if conn is None:
        flash("Database connection failed! Cannot fetch user or manager data.", 'error')
        return render_template('user_form.html', user=None, managers=managers)

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        if user is None:
            flash("User not found.", 'danger')
            return redirect(url_for('users.view_users'))

        cursor.execute("SELECT id, name FROM users WHERE position IN ('Manager', 'Senior') ORDER BY name")
        managers = cursor.fetchall()

    except mysql.connector.Error as err:
        app.logger.error(f"Failed to fetch user {user_id} or managers. Error: {err}")
        flash("Failed to fetch user data or manager list.", 'danger')
    finally:
        cursor.close()
        conn.close()

    return render_template('user_form.html', user=user, managers=managers)

@users_bp.route('/update_user/<int:user_id>', methods=['POST'])
def update_user(user_id):
    """Handles the form submission for updating an existing user."""
    if request.method == 'POST':
        form_data = request.form.to_dict()
        conn = get_db_connection()
        if conn is None:
            return "Database connection failed!", 500

        cursor = conn.cursor()
        sql_parts = []
        val = []
        fields_to_update = [
            'user_type', 'user_name', 'consultant_type', 'reporting_manager',
            'alternate_mobile', 'worksnap_credentials', 'status', 'timesheet_notification',
            'name', 'mobile', 'office_email', 'joining_date', 'position', 'date_of_birth',
            'anniversary_date', 'sap_server_credentials', 'allow_backdated_timesheet'
        ]

        for field in fields_to_update:
            sql_parts.append(f"{field} = %s")
            value = form_data.get(field)
            val.append(value if value else None)

        if form_data.get('password'):
            sql_parts.append("password = %s")
            val.append(form_data.get('password'))

        sql = f"UPDATE users SET {', '.join(sql_parts)} WHERE id = %s"
        val.append(user_id)

        try:
            cursor.execute(sql, tuple(val))
            conn.commit()
            flash("User updated successfully!", 'success')
            return redirect(url_for('users.view_users'))
        except mysql.connector.Error as err:
            conn.rollback()
            app.logger.error(f"Failed to update user {user_id}. Error: {err}")
            error_message = "Failed to update user. An error occurred."
            if err.errno == 1062:
                error_message = "Failed to update user. User Name or Office Email already exists for another user."
            flash(error_message, 'danger')
            return redirect(url_for('users.edit_user', user_id=user_id))
        finally:
            cursor.close()
            conn.close()

@users_bp.route('/delete_user/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Deletes a user from the database based on the provided user_id."""
    conn = get_db_connection()
    if conn is None:
        return jsonify({'error': 'Database connection failed'}), 500

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return jsonify({'error': 'User not found'}), 404
        flash("User has been deleted.", 'success')
        return jsonify({'message': 'User deleted successfully'}), 200
    except mysql.connector.Error as err:
        conn.rollback()
        app.logger.error(f"Failed to delete user {user_id}. Error: {err}")
        return jsonify({'error': 'An internal error occurred.'}), 500
    finally:
        cursor.close()
        conn.close()

@users_bp.route('/attendance', methods=['GET'])
@login_required
def attendance():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    today = date.today()
    now = datetime.now()
    cursor.execute("SELECT * FROM attendance WHERE user_id = %s AND date = %s", (current_user.id, today))
    today_attendance = cursor.fetchone()
    cursor.execute("SELECT * FROM attendance WHERE user_id = %s ORDER BY date DESC LIMIT 7", (current_user.id,))
    attendance_records = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template(
        'attendance.html',
        user=current_user,
        now=now,
        attendance=today_attendance,
        records=attendance_records
    )

@users_bp.route('/attendance/check_in', methods=['POST'])
@login_required
def check_in():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    now = datetime.now()
    today = now.date()
    cursor.execute("SELECT * FROM attendance WHERE user_id = %s AND date = %s", (current_user.id, today))
    record = cursor.fetchone()
    if record and record['check_in']:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': 'Already checked in today.'}), 400
    if record:
        cursor.execute("UPDATE attendance SET check_in = %s WHERE user_id = %s AND date = %s", (now, current_user.id, today))
    else:
        cursor.execute("INSERT INTO attendance (user_id, check_in, date) VALUES (%s, %s, %s)", (current_user.id, now, today))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'check_in': now.strftime('%H:%M:%S')})

@users_bp.route('/attendance/check_out', methods=['POST'])
@login_required
def check_out():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    now = datetime.now()
    today = now.date()
    cursor.execute("SELECT * FROM attendance WHERE user_id = %s AND date = %s", (current_user.id, today))
    record = cursor.fetchone()
    if not record or not record['check_in']:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': 'Check in first.'}), 400
    if record['check_out']:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'message': 'Already checked out today.'}), 400
    cursor.execute("UPDATE attendance SET check_out = %s WHERE user_id = %s AND date = %s", (now, current_user.id, today))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'check_out': now.strftime('%H:%M:%S')})

# --- Blueprint for Ticket Management ---
tickets_bp = Blueprint('tickets', __name__, template_folder='html')

# Ticket management
@tickets_bp.route('/dashboard')
@login_required
@roles_required('Admin', 'Consultant', 'Customer')
def dashboard():
    """Fetches all tickets from the database and displays them on the dashboard."""
    conn = get_db_connection()
    tickets = []
    if conn is None:
        flash("Database connection failed! Cannot retrieve ticket data for dashboard.", 'danger')
        return render_template('dashboard.html', tickets=[])

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT id, ticket_number, customer, subject AS task, priority, status FROM tickets")
        tickets = cursor.fetchall()
        
        for ticket in tickets:
            if 'delivery_date' not in ticket or ticket['delivery_date'] is None:
                ticket['deliveryDate'] = 'N/A'
            if 'task' not in ticket and 'subject' in ticket:
                ticket['task'] = ticket['subject']

    except mysql.connector.Error as err:
        app.logger.error(f"Failed to fetch tickets for dashboard. Error: {err}")
        flash("Failed to load ticket data for dashboard. An error occurred.", 'danger')
    finally:
        cursor.close()
        conn.close()

    return render_template('dashboard.html', tickets=tickets)

@tickets_bp.route('/assign_tickets')
@login_required
@roles_required('Admin', 'Consultant', 'Customer')
def assign_tickets():
    """
    Fetches open and assigned tickets, and a list of admins/consultants
    to display on the ticket assignment page.
    """
    conn = get_db_connection()
    open_tickets = []
    assigned_tickets = []
    assignees = [] # Admins and Consultants

    if not conn:
        flash('Database connection failed. Cannot load data for ticket assignment.', 'error')
        return render_template('assign_tickets.html', open_tickets=[], assigned_tickets=[], assignees=[])

    cursor = conn.cursor(dictionary=True)
    try:
        # Fetch OPEN tickets
        cursor.execute("SELECT id, ticket_number, subject, customer, status, assigned_to_user_name FROM tickets WHERE status = 'Open' ORDER BY ticket_number ASC")
        open_tickets = cursor.fetchall()

        # Fetch ASSIGNED tickets
        cursor.execute("SELECT id, ticket_number, subject, customer, status, assigned_to_user_name FROM tickets WHERE status = 'Assigned' ORDER BY ticket_number ASC")
        assigned_tickets = cursor.fetchall()

        # Fetch users with user_type 'Admin' or 'Consultant'
        cursor.execute("SELECT id, name, user_type FROM users WHERE user_type IN ('Admin', 'Consultant') ORDER BY name ASC")
        assignees = cursor.fetchall()

    except mysql.connector.Error as err:
        app.logger.error(f"Database Error loading assign_tickets page: {err}")
        flash('Error loading ticket assignment data.', 'error')
    finally:
        cursor.close()
        conn.close()

    return render_template('assign_tickets.html', open_tickets=open_tickets, assigned_tickets=assigned_tickets, assignees=assignees)

@tickets_bp.route('/new_task', methods=['GET'])
@login_required
@roles_required('Admin', 'Consultant', 'Customer')
def new_task():
    """Renders the main ticket submission form."""
    conn = get_db_connection()
    next_ticket_no = 25649

    customers = []

    if not conn:
        flash('Database connection failed. Cannot generate new ticket number or fetch customers.', 'error')
        return render_template('new_task.html', next_ticket_no=next_ticket_no, customers=customers)

    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT MAX(CAST(ticket_number AS UNSIGNED)) FROM tickets")
        max_ticket = cursor.fetchone()['MAX(CAST(ticket_number AS UNSIGNED))']
        if max_ticket is not None:
            next_ticket_no = int(max_ticket) + 1
        else:
            next_ticket_no = 1

        cursor.execute("SELECT id, name, office_email FROM users WHERE user_type = 'customer' ORDER BY name")
        customers = cursor.fetchall()

    except mysql.connector.Error as err:
        app.logger.error(f"Database Error in new_task route: {err}")
        flash('Could not fetch data from the database.', 'error')
    finally:
        cursor.close()
        conn.close()

    return render_template('new_task.html', next_ticket_no=next_ticket_no, customers=customers, edit_mode=False)


@tickets_bp.route('/submit_ticket', methods=['POST'])
def submit_ticket():
    """Handles form submission, file upload, and database insertion."""
    ticket_data = {
        'ticket_no': request.form.get('ticket_no'),
        'customer': request.form.get('customer'),
        'module': request.form.get('module'),
        'status': request.form.get('status'),
        'form_type': request.form.get('form_type'),
        'priority': request.form.get('priority'),
        'subject': request.form.get('subject'),
        'task_given_by': request.form.get('task_given_by'),
        'approved_hours': request.form.get('approved_hours'),
        'description': request.form.get('description')
    }

    attachment_path = None
    if 'attachment' in request.files:
        file = request.files['attachment']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
            attachment_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(attachment_path)

    conn = get_db_connection()
    if not conn:
        flash('Database connection failed. Please check server logs.', 'error')
        return redirect(url_for('tickets.new_task'))

    cursor = conn.cursor()
    sql_query = """
    INSERT INTO tickets (
        ticket_number, customer, module, status, form_type, priority,
        subject, task_given_by, approved_hours, description, attachment_path
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (
        ticket_data['ticket_no'], ticket_data['customer'], ticket_data['module'],
        ticket_data['status'], ticket_data['form_type'], ticket_data['priority'],
        ticket_data['subject'], ticket_data['task_given_by'],
        ticket_data['approved_hours'], ticket_data['description'], attachment_path
    )

    try:
        cursor.execute(sql_query, values)
        conn.commit()
        flash('Ticket submitted successfully!', 'success')
        return redirect(url_for('tickets.dashboard'))
    except mysql.connector.Error as err:
        app.logger.error(f"Database Error: {err}")
        flash(f'Failed to submit ticket. Database error: {err}', 'error')
        return redirect(url_for('tickets.new_task'))
    finally:
        cursor.close()
        conn.close()


@tickets_bp.route('/edit_ticket/<int:ticket_id>', methods=['GET'])
def edit_ticket(ticket_id):
    """Fetches a single ticket's data for editing."""
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed.', 'error')
        return redirect(url_for('tickets.dashboard'))

    cursor = conn.cursor(dictionary=True)
    ticket = None
    customers = []
    try:
        cursor.execute("SELECT * FROM tickets WHERE id = %s", (ticket_id,))
        ticket = cursor.fetchone()

        if not ticket:
            flash('Ticket not found!', 'error')
            return redirect(url_for('tickets.dashboard'))

        cursor.execute("SELECT id, name FROM users WHERE user_type = 'customer' ORDER BY name")
        customers = cursor.fetchall()
        
    except mysql.connector.Error as err:
        app.logger.error(f"Database Error fetching ticket for edit: {err}")
        flash('An error occurred while fetching ticket data.', 'error')
        return redirect(url_for('tickets.dashboard'))
    finally:
        cursor.close()
        conn.close()
    
    return render_template('new_task.html', ticket=ticket, customers=customers, edit_mode=True)


@tickets_bp.route('/update_ticket/<int:ticket_id>', methods=['POST'])
def update_ticket(ticket_id):
    """Handles updating the ticket in the database."""
    form_data = request.form
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed.', 'error')
        return redirect(url_for('tickets.edit_ticket', ticket_id=ticket_id))

    cursor = conn.cursor()
    sql_query = """
    UPDATE tickets SET
        customer = %s,
        module = %s,
        status = %s,
        form_type = %s,
        priority = %s,
        subject = %s,
        task_given_by = %s,
        approved_hours = %s,
        description = %s
    WHERE id = %s
    """
    values = (
        form_data.get('customer'),
        form_data.get('module'),
        form_data.get('status'),
        form_data.get('form_type'),
        form_data.get('priority'),
        form_data.get('subject'),
        form_data.get('task_given_by'),
        form_data.get('approved_hours'),
        form_data.get('description'),
        ticket_id
    )

    try:
        cursor.execute(sql_query, values)
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                if not os.path.exists(app.config['UPLOAD_FOLDER']):
                    os.makedirs(app.config['UPLOAD_FOLDER'])
                attachment_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(attachment_path)
                cursor.execute("UPDATE tickets SET attachment_path = %s WHERE id = %s", (attachment_path, ticket_id))

        conn.commit()
        flash('Ticket updated successfully!', 'success')
    except mysql.connector.Error as err:
        conn.rollback()
        app.logger.error(f"Database Error on ticket update: {err}")
        flash(f'Failed to update ticket. Database error: {err}', 'error')
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('tickets.dashboard'))



@tickets_bp.route('/perform_assignment', methods=['POST'])
def perform_assignment():
    """
    Handles the AJAX request to assign a ticket to a user.
    Expects JSON data: {'ticket_id': <int>, 'assignee_name': <str>}
    Returns the updated ticket data on success.
    """
    if request.is_json:
        data = request.get_json()
        ticket_id = data.get('ticket_id')
        assignee_names = data.get('assignee_names')
        if isinstance(assignee_names, list):
            assignee_names_str = ', '.join(assignee_names)
        else:
            assignee_names_str = str(assignee_names) if assignee_names else ''

        if not ticket_id or not assignee_names_str:
            return jsonify({'success': False, 'message': 'Missing ticket ID or assignee name.'}), 400

        conn = get_db_connection()
        if not conn:
            return jsonify({'success': False, 'message': 'Database connection failed.'}), 500

        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "UPDATE tickets SET assigned_to_user_name = %s, status = 'Assigned' WHERE id = %s",
                (assignee_names_str, ticket_id)
            )
            conn.commit()

            if cursor.rowcount == 0:
                return jsonify({'success': False, 'message': 'Ticket not found or no changes made.'}), 404

            # Fetch the updated ticket data to send back to the frontend
            cursor.execute("SELECT id, ticket_number, subject, customer, status, assigned_to_user_name FROM tickets WHERE id = %s", (ticket_id,))
            updated_ticket = cursor.fetchone()

            # Defensive: If fetch fails, still return success
            if not updated_ticket:
                updated_ticket = {
                    'id': ticket_id,
                    'ticket_number': '',
                    'subject': '',
                    'customer': '',
                    'status': 'Assigned',
                    'assigned_to_user_name': assignee_names_str
                }

            return jsonify({'success': True, 'message': f'Ticket {ticket_id} assigned to {assignee_names_str} successfully.', 'ticket': updated_ticket}), 200
        except Exception as err:
            conn.rollback()
            app.logger.error(f"Error assigning ticket {ticket_id}: {err}")
            return jsonify({'success': False, 'message': f'Database error: {err}'}), 500
        finally:
            cursor.close()
            conn.close()
    else:
        return jsonify({'success': False, 'message': 'Request must be JSON.'}), 400


holidays_bp = Blueprint('holidays', __name__, template_folder='html')

# Holidays (Admin/Consultant only)
@holidays_bp.route('/list')
@login_required
@roles_required('Admin', 'Consultant')
def holiday_list():
    """Renders the holiday management page, fetching data from MySQL."""
    conn = get_db_connection()
    holidays = []
    
    filter_type = request.args.get('filter_type', 'all')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    start_date_filter = None
    end_date_filter = None

    current_date = date.today()

    if filter_type == 'this_month':
        start_date_filter = current_date.replace(day=1)
        if current_date.month == 12:
            end_date_filter = current_date.replace(year=current_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date_filter = current_date.replace(month=current_date.month + 1, day=1) - timedelta(days=1)
    elif filter_type == 'this_week':
        start_date_filter = current_date - timedelta(days=current_date.weekday())
        end_date_filter = start_date_filter + timedelta(days=6)
    elif filter_type == 'today':
        start_date_filter = current_date
        end_date_filter = current_date
    elif filter_type == 'custom_range':
        try:
            if start_date_str:
                start_date_filter = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            if end_date_str:
                end_date_filter = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash("Invalid date format for custom range. Please use YYYY-MM-DD.", 'error')
            start_date_filter = None
            end_date_filter = None


    if not conn:
        flash('Database connection failed.', 'error')
        return render_template('holiday.html', holidays=holidays, filter_type=filter_type, 
                               start_date=start_date_str, end_date=end_date_str)
    
    cursor = conn.cursor(dictionary=True)
    try:
        sql_query = "SELECT id, country, name, holiday_date FROM holidays"
        params = []
        where_clauses = []

        if start_date_filter and end_date_filter:
            where_clauses.append("holiday_date BETWEEN %s AND %s")
            params.append(start_date_filter)
            params.append(end_date_filter)
        elif start_date_filter:
            where_clauses.append("holiday_date >= %s")
            params.append(start_date_filter)
        elif end_date_filter:
            where_clauses.append("holiday_date <= %s")
            params.append(end_date_filter)
        
        if where_clauses:
            sql_query += " WHERE " + " AND ".join(where_clauses)
            
        sql_query += " ORDER BY holiday_date ASC"

        cursor.execute(sql_query, tuple(params))
        holidays = cursor.fetchall()

        for holiday in holidays:
            if isinstance(holiday['holiday_date'], datetime):
                holiday['display_date'] = holiday['holiday_date'].strftime('%d/%m/%Y')
                holiday['form_date'] = holiday['holiday_date'].strftime('%Y-%m-%d')
            elif isinstance(holiday['holiday_date'], date):
                holiday['display_date'] = holiday['holiday_date'].strftime('%d/%m/%Y')
                holiday['form_date'] = holiday['holiday_date'].strftime('%Y-%m-%d')
            elif isinstance(holiday['holiday_date'], str):
                try:
                    dt = datetime.strptime(holiday['holiday_date'], '%Y-%m-%d').date()
                    holiday['display_date'] = dt.strftime('%d/%m/%Y')
                    holiday['form_date'] = dt.strftime('%Y-%m-%d')
                except Exception:
                    holiday['display_date'] = holiday['holiday_date']
                    holiday['form_date'] = holiday['holiday_date']
            else:
                holiday['display_date'] = ''
                holiday['form_date'] = ''

    except mysql.connector.Error as err:
        app.logger.error(f"Error fetching holidays: {err}")
        flash('Could not fetch holiday data from the database.', 'error')
    finally:
        cursor.close()
        conn.close()
        
    return render_template('holiday.html', holidays=holidays, filter_type=filter_type, 
                           start_date=start_date_str, end_date=end_date_str)

@holidays_bp.route('/add', methods=['POST'])
def add_holiday():
    """Handles adding a new holiday to the MySQL database."""
    country = request.form.get('country')
    name = request.form.get('holiday_name')
    date = request.form.get('holiday_date')

    if not country or not name or not date:
        flash('All fields are required!', 'error')
        return redirect(url_for('holidays.holiday_list'))

    conn = get_db_connection()
    if not conn:
        flash('Database connection failed.', 'error')
        return redirect(url_for('holidays.holiday_list'))
        
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO holidays (country, name, holiday_date) VALUES (%s, %s, %s)",
            (country, name, date)
        )
        conn.commit()
        flash('Holiday added successfully!', 'success')
    except mysql.connector.Error as err:
        conn.rollback()
        app.logger.error(f"Error adding holiday: {err}")
        flash('Failed to add holiday.', 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('holidays.holiday_list'))

@holidays_bp.route('/update/<int:holiday_id>', methods=['POST'])
def update_holiday(holiday_id):
    """Handles updating an existing holiday in the MySQL database."""
    country = request.form.get('country')
    name = request.form.get('holiday_name')
    date = request.form.get('holiday_date')

    if not country or not name or not date:
        flash('All fields are required for an update!', 'error')
        return redirect(url_for('holidays.holiday_list'))

    conn = get_db_connection()
    if not conn:
        flash('Database connection failed.', 'error')
        return redirect(url_for('holidays.holiday_list'))
        
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE holidays SET country = %s, name = %s, holiday_date = %s WHERE id = %s",
            (country, name, date, holiday_id)
        )
        conn.commit()
        flash('Holiday updated successfully!', 'success')
    except mysql.connector.Error as err:
        conn.rollback()
        app.logger.error(f"Error updating holiday: {err}")
        flash('Failed to update holiday.', 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('holidays.holiday_list'))

@holidays_bp.route('/delete/<int:holiday_id>')
def delete_holiday(holiday_id):
    """Deletes a holiday from the MySQL database."""
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed.', 'error')
        return redirect(url_for('holidays.holiday_list'))
        
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM holidays WHERE id = %s", (holiday_id,))
        conn.commit()
        flash('Holiday deleted successfully!', 'danger')
    except mysql.connector.Error as err:
        conn.rollback()
        app.logger.error(f"Error deleting holiday: {err}")
        flash('Failed to delete holiday.', 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('holidays.holiday_list'))


# --- NEW: Blueprint for Leave Management ---
leave_bp = Blueprint('leaves', __name__, template_folder='html')

# Leaves (Admin/Consultant only)
@leave_bp.route('/list')
@login_required
@roles_required('Admin', 'Consultant')
def leave_list():
    """Renders the leave request page, fetching data from MySQL, with date filtering."""
    conn = get_db_connection()
    leaves = []
    
    filter_type = request.args.get('filter_type', 'all')
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')

    start_date_filter = None
    end_date_filter = None

    current_date = date.today()

    if filter_type == 'this_month':
        start_date_filter = current_date.replace(day=1)
        if current_date.month == 12:
            end_date_filter = current_date.replace(year=current_date.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end_date_filter = current_date.replace(month=current_date.month + 1, day=1) - timedelta(days=1)
    elif filter_type == 'this_week':
        start_date_filter = current_date - timedelta(days=current_date.weekday())
        end_date_filter = start_date_filter + timedelta(days=6)
    elif filter_type == 'today':
        start_date_filter = current_date
        end_date_filter = current_date
    elif filter_type == 'custom_range':
        try:
            if start_date_str:
                start_date_filter = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            if end_date_str:
                end_date_filter = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        except ValueError:
            flash("Invalid date format for custom range. Please use YYYY-MM-DD.", 'error')
            start_date_filter = None
            end_date_filter = None

    if not conn:
        flash('Database connection failed.', 'error')
        return render_template('leave_request.html', leaves=leaves, filter_type=filter_type, 
                               start_date=start_date_str, end_date=end_date_str, user=current_user)
    
    cursor = conn.cursor(dictionary=True)
    try:
        sql_query = "SELECT id, consultant_name, leave_date, leave_type, remarks FROM leave_requests"
        params = []
        where_clauses = []

        if start_date_filter and end_date_filter:
            where_clauses.append("leave_date BETWEEN %s AND %s")
            params.append(start_date_filter)
            params.append(end_date_filter)
        elif start_date_filter:
            where_clauses.append("leave_date >= %s")
            params.append(start_date_filter)
        elif end_date_filter:
            where_clauses.append("leave_date <= %s")
            params.append(end_date_filter)
        
        if where_clauses:
            sql_query += " WHERE " + " AND ".join(where_clauses)
            
        sql_query += " ORDER BY leave_date DESC, created_at DESC"

        cursor.execute(sql_query, tuple(params))
        leaves = cursor.fetchall()
        
        for leave in leaves:
            if isinstance(leave['leave_date'], datetime):
                leave['display_date'] = leave['leave_date'].strftime('%d/%m/%Y')
                leave['form_date'] = leave['leave_date'].strftime('%Y-%m-%d')
            elif isinstance(leave['leave_date'], date):
                leave['display_date'] = leave['leave_date'].strftime('%d/%m/%Y')
                leave['form_date'] = leave['leave_date'].strftime('%Y-%m-%d')
            elif isinstance(leave['leave_date'], str):
                try:
                    dt = datetime.strptime(leave['leave_date'], '%Y-%m-%d').date()
                    leave['display_date'] = dt.strftime('%d/%m/%Y')
                    leave['form_date'] = dt.strftime('%Y-%m-%d')
                except Exception:
                    leave['display_date'] = leave['leave_date']
                    leave['form_date'] = leave['leave_date']
            else:
                leave['display_date'] = ''
                leave['form_date'] = ''
    except mysql.connector.Error as err:
        app.logger.error(f"Error fetching leave requests: {err}")
        flash('Could not fetch leave request data from the database.', 'error')
    finally:
        cursor.close()
        conn.close()
        
    return render_template('leave_request.html', leaves=leaves, filter_type=filter_type, 
                           start_date=start_date_str, end_date=end_date_str, user=current_user)

@leave_bp.route('/add', methods=['POST'])
def add_leave():
    """Handles adding a new leave request to the MySQL database."""
    consultant_name = request.form.get('consultant_name')
    leave_date = request.form.get('leave_date')
    leave_type = request.form.get('leave_type')
    remarks = request.form.get('remarks')

    if not consultant_name or not leave_date or not leave_type:
        flash('Consultant Name, Leave Date, and Leave Type are required!', 'error')
        return redirect(url_for('leaves.leave_list'))

    conn = get_db_connection()
    if not conn:
        flash('Database connection failed.', 'error')
        return redirect(url_for('leaves.leave_list'))
        
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO leave_requests (consultant_name, leave_date, leave_type, remarks) VALUES (%s, %s, %s, %s)",
            (consultant_name, leave_date, leave_type, remarks)
        )
        conn.commit()
        flash('Leave request added successfully!', 'success')
    except mysql.connector.Error as err:
        conn.rollback()
        app.logger.error(f"Error adding leave request: {err}")
        flash('Failed to add leave request. A request for this date/consultant might already exist or invalid data.', 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('leaves.leave_list'))

@leave_bp.route('/update/<int:leave_id>', methods=['POST'])
def update_leave(leave_id):
    """Handles updating an existing leave request in the MySQL database."""
    consultant_name = request.form.get('consultant_name')
    leave_date = request.form.get('leave_date')
    leave_type = request.form.get('leave_type')
    remarks = request.form.get('remarks')

    if not consultant_name or not leave_date or not leave_type:
        flash('Consultant Name, Leave Date, and Leave Type are required for an update!', 'error')
        return redirect(url_for('leaves.leave_list'))

    conn = get_db_connection()
    if not conn:
        flash('Database connection failed.', 'error')
        return redirect(url_for('leaves.leave_list'))
        
    cursor = conn.cursor()
    try:
        cursor.execute(
            "UPDATE leave_requests SET consultant_name = %s, leave_date = %s, leave_type = %s, remarks = %s WHERE id = %s",
            (consultant_name, leave_date, leave_type, remarks, leave_id)
        )
        conn.commit()
        flash('Leave request updated successfully!', 'success')
    except mysql.connector.Error as err:
        conn.rollback()
        app.logger.error(f"Error updating leave request: {err}")
        flash('Failed to update leave request. An error occurred.', 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('leaves.leave_list'))

@leave_bp.route('/delete/<int:leave_id>')
def delete_leave(leave_id):
    """Deletes a leave request from the MySQL database."""
    conn = get_db_connection()
    if not conn:
        flash('Database connection failed.', 'error')
        return redirect(url_for('leaves.leave_list'))
        
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM leave_requests WHERE id = %s", (leave_id,))
        conn.commit()
        flash('Leave request deleted successfully!', 'danger')
    except mysql.connector.Error as err:
        conn.rollback()
        app.logger.error(f"Error deleting leave request: {err}")
        flash('Failed to delete leave request.', 'error')
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('leaves.leave_list'))


# --- NEW: Roles Required Decorator ---



# --- Register Blueprints with the main app ---
app.register_blueprint(users_bp, url_prefix='/')
app.register_blueprint(tickets_bp, url_prefix='/tickets')
app.register_blueprint(holidays_bp, url_prefix='/holidays')
app.register_blueprint(leave_bp, url_prefix='/leaves')

# --- Login Manager Setup ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'  # endpoint name for login

class User(UserMixin):
    def __init__(self, id, user_name, password, user_type, name):
        self.id = id
        self.user_name = user_name
        self.password = password
        self.user_type = user_type
        self.name = name  # <-- Add this line

    def get_id(self):
        return str(self.id)

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if user:
        # Add user['name'] here
        return User(user['id'], user['user_name'], user['password'], user['user_type'], user['name'])
    return None

# --- Login and Logout Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_name = request.form['user_name']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE user_name = %s", (user_name,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()
        if user and check_password_hash(user['password'], password):
            user_obj = User(user['id'], user['user_name'], user['password'], user['user_type'], user['name'])  # <-- FIXED
            login_user(user_obj)
            flash('Logged in successfully!', 'success')
            return redirect(url_for('tickets.dashboard'))
        else:
            flash('Invalid username or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('login'))

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form['current_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash('New passwords do not match.', 'danger')
            return render_template('change_password.html', user=current_user)

        # Fetch the current user's hashed password from DB
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT password FROM users WHERE id = %s", (current_user.id,))
        user = cursor.fetchone()
        if not user or not check_password_hash(user['password'], current_password):
            flash('Current password is incorrect.', 'danger')
            cursor.close()
            conn.close()
            return render_template('change_password.html', user=current_user)

        # Update password
        hashed_password = generate_password_hash(new_password)
        cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_password, current_user.id))
        conn.commit()
        cursor.close()
        conn.close()
        flash('Password changed successfully!', 'success')
        return redirect(url_for('tickets.dashboard'))

    return render_template('change_password.html', user=current_user)

# --- Main Execution ---
if __name__ == '__main__':
    # Make sure the 'uploads' directory exists
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
    app.run(debug=True)