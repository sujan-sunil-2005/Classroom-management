from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
import mysql.connector
from db_config import db_config
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = 'classroom_secret_key_2025'  # Replace with a secure key in production

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, user_id, username, role):
        self.id = user_id
        self.username = username
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("USE classroom_management")
    cursor.execute("SELECT user_id, username, role FROM users WHERE user_id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    if user_data:
        return User(user_data[0], user_data[1], user_data[2])
    return None

def get_db_connection():
    return mysql.connector.connect(**db_config)

@app.route('/')
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")
        if current_user.role == 'admin':
            # Admins can see all bookings
            cursor.execute("""
                SELECT b.booking_id, r.room_name, b.date, b.time_slot, b.teacher, b.section, b.course_code
                FROM bookings b
                JOIN rooms r ON b.room_id = r.room_id
                ORDER BY b.date, b.time_slot
            """)
        else:
            # Teachers can only see their own bookings
            cursor.execute("""
                SELECT b.booking_id, r.room_name, b.date, b.time_slot, b.teacher, b.section, b.course_code
                FROM bookings b
                JOIN rooms r ON b.room_id = r.room_id
                WHERE b.teacher = %s
                ORDER BY b.date, b.time_slot
            """, (current_user.username,))
        bookings = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('bookings.html', bookings=bookings)
    except Exception as e:
        print(f"Error in index route: {e}")
        flash(f"An error occurred: {e}")
        return render_template('bookings.html', bookings=[])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("USE classroom_management")
            cursor.execute("SELECT user_id, username, role FROM users WHERE username = %s AND password = %s", (username, password))
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()
            if user_data:
                user = User(user_data[0], user_data[1], user_data[2])
                login_user(user)
                flash('Logged in successfully!')
                return redirect(url_for('index'))
            else:
                flash('Invalid username or password.')
                return redirect(url_for('login'))
        except Exception as e:
            print(f"Error in login route: {e}")
            flash(f"An error occurred: {e}")
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully!')
    return redirect(url_for('login'))

@app.route('/check_availability', methods=['POST'])
def check_availability():
    try:
        data = request.get_json()
        room_id = data.get('room_id')
        date = data.get('date')
        time_slot = data.get('time_slot')

        if not all([room_id, date, time_slot]):
            return jsonify({'available': False, 'message': 'Missing required fields'})

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")
        cursor.execute("""
            SELECT booking_id
            FROM bookings
            WHERE room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
        """, (room_id, date, time_slot))
        booking_conflict = cursor.fetchone()

        if booking_conflict:
            return jsonify({'available': False, 'message': 'This slot is already booked'})

        # Check for active reservations
        cursor.execute("""
            SELECT reservation_id
            FROM reservations
            WHERE room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
            AND expires_at > NOW()
        """, (room_id, date, time_slot))
        reservation_conflict = cursor.fetchone()

        if reservation_conflict:
            return jsonify({'available': False, 'message': 'This slot is temporarily reserved'})

        return jsonify({'available': True, 'message': 'This slot is available'})
    except Exception as e:
        print(f"Error in check_availability route: {e}")
        return jsonify({'available': False, 'message': f'Error: {e}'})

@app.route('/get_bookings', methods=['GET'])
@login_required
def get_bookings():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")
        # Fetch all bookings for the calendar
        cursor.execute("""
            SELECT b.date, b.time_slot, r.room_name
            FROM bookings b
            JOIN rooms r ON b.room_id = r.room_id
        """)
        bookings = cursor.fetchall()
        cursor.close()
        conn.close()

        events = []
        for booking in bookings:
            date = booking[0].strftime('%Y-%m-%d')
            time_slot = booking[1]
            room_name = booking[2]
            events.append({
                'title': f'{room_name} - {time_slot}',
                'start': date,
                'backgroundColor': '#e63946',  # Red for booked
                'borderColor': '#e63946',
                'textColor': '#fff'
            })
        return jsonify(events)
    except Exception as e:
        print(f"Error in get_bookings route: {e}")
        return jsonify([])

@app.route('/get_available_time_slots', methods=['POST'])
@login_required
def get_available_time_slots():
    try:
        data = request.get_json()
        room_id = data.get('room_id')
        date = data.get('date')

        if not all([room_id, date]):
            return jsonify({'time_slots': []})

        # All possible time slots
        all_time_slots = [
            '08:30-09:30', '09:30-10:30', '11:00-12:00', '12:00-13:00',
            '14:00-15:00', '15:00-16:00'
        ]

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")
        cursor.execute("""
            SELECT time_slot
            FROM bookings
            WHERE room_id = %s AND DATE(date) = DATE(%s)
        """, (room_id, date))
        booked_slots = [row[0].strip() for row in cursor.fetchall()]

        # Check for reserved slots
        cursor.execute("""
            SELECT time_slot
            FROM reservations
            WHERE room_id = %s AND DATE(date) = DATE(%s) AND expires_at > NOW()
        """, (room_id, date))
        reserved_slots = [row[0].strip() for row in cursor.fetchall()]

        # Filter out booked and reserved slots
        available_slots = [slot for slot in all_time_slots if slot not in booked_slots and slot not in reserved_slots]
        cursor.close()
        conn.close()
        return jsonify({'time_slots': available_slots})
    except Exception as e:
        print(f"Error in get_available_time_slots route: {e}")
        return jsonify({'time_slots': []})

@app.route('/room_status', methods=['GET', 'POST'])
@login_required
def room_status():
    selected_date = request.form.get('date') if request.method == 'POST' else None
    if not selected_date:
        # Default to today if no date is selected
        selected_date = datetime.now().strftime('%Y-%m-%d')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")

        # Fetch all rooms
        cursor.execute("SELECT room_id, room_name FROM rooms")
        rooms = cursor.fetchall()

        # Fetch bookings for the selected date with booking_id for edit functionality
        cursor.execute("""
            SELECT b.booking_id, r.room_name, b.time_slot, b.teacher, b.section, b.course_code
            FROM bookings b
            JOIN rooms r ON b.room_id = r.room_id
            WHERE DATE(b.date) = DATE(%s)
            ORDER BY r.room_name, b.time_slot
        """, (selected_date,))
        bookings = cursor.fetchall()

        # Fetch existing slot requests by the current user for the selected date
        cursor.execute("""
            SELECT r.room_name, sr.time_slot
            FROM slot_requests sr
            JOIN rooms r ON sr.room_id = r.room_id
            WHERE sr.teacher = %s AND DATE(sr.date) = DATE(%s)
        """, (current_user.username, selected_date))
        user_requests = cursor.fetchall()
        requested_slots = {(room_name, time_slot) for room_name, time_slot in user_requests}

        # Fetch reserved slots for the selected date
        cursor.execute("""
            SELECT r.room_name, res.time_slot
            FROM reservations res
            JOIN rooms r ON res.room_id = r.room_id
            WHERE DATE(res.date) = DATE(%s) AND res.expires_at > NOW()
        """, (selected_date,))
        reserved_slots = {(room_name, time_slot) for room_name, time_slot in cursor.fetchall()}

        cursor.close()
        conn.close()

        # Organize bookings by room and time slot
        time_slots = [
            '08:30-09:30', '09:30-10:30', '11:00-12:00', '12:00-13:00',
            '14:00-15:00', '15:00-16:00'
        ]
        room_status = {room[1]: {slot: None for slot in time_slots} for room in rooms}

        for booking in bookings:
            booking_id, room_name, time_slot, teacher, section, course_code = booking
            room_status[room_name][time_slot] = {
                'booking_id': booking_id,
                'teacher': teacher,
                'section': section,
                'course_code': course_code
            }

        return render_template('room_status.html', room_status=room_status, time_slots=time_slots, selected_date=selected_date, requested_slots=requested_slots, reserved_slots=reserved_slots)
    except Exception as e:
        print(f"Error in room_status route: {e}")
        flash(f"An error occurred: {e}")
        return render_template('room_status.html', room_status={}, time_slots=[], selected_date=selected_date, requested_slots=set(), reserved_slots=set())

@app.route('/request_slot', methods=['POST'])
@login_required
def request_slot():
    try:
        room_name = request.form.get('room_name')
        date = request.form.get('date')
        time_slot = request.form.get('time_slot')

        if not all([room_name, date, time_slot]):
            flash('Missing required fields.')
            return redirect(url_for('room_status'))

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")

        # Get room_id from room_name
        cursor.execute("SELECT room_id FROM rooms WHERE room_name = %s", (room_name,))
        room = cursor.fetchone()
        if not room:
            flash('Invalid room.')
            cursor.close()
            conn.close()
            return redirect(url_for('room_status'))
        room_id = room[0]

        # Check if the slot is already booked
        cursor.execute("""
            SELECT booking_id
            FROM bookings
            WHERE room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
        """, (room_id, date, time_slot))
        if cursor.fetchone():
            flash('Cannot request a slot that is already booked.')
            cursor.close()
            conn.close()
            return redirect(url_for('room_status'))

        # Check if the slot is already reserved by someone else
        cursor.execute("""
            SELECT reservation_id
            FROM reservations
            WHERE room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
            AND expires_at > NOW()
        """, (room_id, date, time_slot))
        if cursor.fetchone():
            flash('This slot is temporarily reserved by another teacher.')
            cursor.close()
            conn.close()
            return redirect(url_for('room_status'))

        # Check if the teacher already requested this slot
        cursor.execute("""
            SELECT request_id
            FROM slot_requests
            WHERE teacher = %s AND room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
        """, (current_user.username, room_id, date, time_slot))
        if cursor.fetchone():
            flash('You have already requested this slot.')
            cursor.close()
            conn.close()
            return redirect(url_for('room_status'))

        # Create a reservation with 15-minute expiration
        expires_at = datetime.now() + timedelta(minutes=15)
        cursor.execute("""
            INSERT INTO reservations (teacher, room_id, date, time_slot, expires_at)
            VALUES (%s, %s, %s, %s, %s)
        """, (current_user.username, room_id, date, time_slot, expires_at))

        # Record the request
        cursor.execute("""
            INSERT INTO slot_requests (teacher, room_id, date, time_slot)
            VALUES (%s, %s, %s, %s)
        """, (current_user.username, room_id, date, time_slot))
        conn.commit()

        flash('Slot requested and reserved for 15 minutes. Please book it soon!')
        cursor.close()
        conn.close()
        return redirect(url_for('room_status'))
    except Exception as e:
        print(f"Error in request_slot route: {e}")
        flash(f"An error occurred: {e}")
        return redirect(url_for('room_status'))

@app.route('/delete_from_room_status/<int:booking_id>', methods=['POST'])
@login_required
def delete_from_room_status(booking_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")

        # Fetch the booking details before deletion
        cursor.execute("""
            SELECT b.room_id, r.room_name, b.date, b.time_slot, b.teacher
            FROM bookings b
            JOIN rooms r ON b.room_id = r.room_id
            WHERE b.booking_id = %s
        """, (booking_id,))
        booking = cursor.fetchone()

        if not booking:
            flash('Booking not found.')
            cursor.close()
            conn.close()
            return redirect(url_for('room_status'))

        room_id, room_name, date, time_slot, teacher = booking

        # Allow deletion only if the user is an admin or the teacher who made the booking
        if current_user.role != 'admin' and current_user.username != teacher:
            flash('You do not have permission to delete this booking.')
            cursor.close()
            conn.close()
            return redirect(url_for('room_status'))

        # Check for slot requests matching this slot
        cursor.execute("""
            SELECT teacher
            FROM slot_requests
            WHERE room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
        """, (room_id, date, time_slot))
        requested_teachers = [row[0] for row in cursor.fetchall()]

        # Delete the booking
        cursor.execute("DELETE FROM bookings WHERE booking_id = %s", (booking_id,))
        conn.commit()

        # Send notifications
        if requested_teachers:
            # Priority notification for teachers who requested the slot
            for req_teacher in requested_teachers:
                priority_message = f"Priority Alert: Your requested slot for {room_name} on {date.strftime('%Y-%m-%d')} at {time_slot} is now available!"
                cursor.execute("INSERT INTO notifications (message) VALUES (%s)", (priority_message,))
            # Remove the slot requests and reservations since the slot is now available
            cursor.execute("""
                DELETE FROM slot_requests
                WHERE room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
            """, (room_id, date, time_slot))
            cursor.execute("""
                DELETE FROM reservations
                WHERE room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
            """, (room_id, date, time_slot))
        else:
            # General notification for all teachers
            notification_message = f"Slot Available: {room_name} on {date.strftime('%Y-%m-%d')} at {time_slot} has been freed up."
            cursor.execute("INSERT INTO notifications (message) VALUES (%s)", (notification_message,))

        conn.commit()

        flash('Booking deleted successfully! A notification has been sent to all teachers.')
        cursor.close()
        conn.close()
        return redirect(url_for('room_status'))
    except Exception as e:
        print(f"Error in delete_from_room_status route: {e}")
        flash(f"An error occurred: {e}")
        return redirect(url_for('room_status'))

@app.route('/notifications')
@login_required
def notifications():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")
        cursor.execute("SELECT notification_id, message, created_at FROM notifications ORDER BY created_at DESC")
        notifications = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('notifications.html', notifications=notifications)
    except Exception as e:
        print(f"Error in notifications route: {e}")
        flash(f"An error occurred: {e}")
        return render_template('notifications.html', notifications=[])

@app.route('/my_slot_requests', methods=['GET'])
@login_required
def my_slot_requests():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")
        cursor.execute("""
            SELECT sr.request_id, r.room_name, sr.date, sr.time_slot, sr.created_at
            FROM slot_requests sr
            JOIN rooms r ON sr.room_id = r.room_id
            WHERE sr.teacher = %s
            ORDER BY sr.created_at DESC
        """, (current_user.username,))
        requests = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('my_slot_requests.html', requests=requests)
    except Exception as e:
        print(f"Error in my_slot_requests route: {e}")
        flash(f"An error occurred: {e}")
        return render_template('my_slot_requests.html', requests=[])

@app.route('/delete_request/<int:request_id>', methods=['POST'])
@login_required
def delete_request(request_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")
        cursor.execute("SELECT teacher FROM slot_requests WHERE request_id = %s", (request_id,))
        request_data = cursor.fetchone()
        if not request_data:
            flash('Request not found.')
            cursor.close()
            conn.close()
            return redirect(url_for('my_slot_requests'))

        if request_data[0] != current_user.username:
            flash('You do not have permission to delete this request.')
            cursor.close()
            conn.close()
            return redirect(url_for('my_slot_requests'))

        # Delete the request and associated reservation
        cursor.execute("SELECT room_id, date, time_slot FROM slot_requests WHERE request_id = %s", (request_id,))
        request_details = cursor.fetchone()
        if request_details:
            room_id, date, time_slot = request_details
            cursor.execute("""
                DELETE FROM reservations
                WHERE teacher = %s AND room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
            """, (current_user.username, room_id, date, time_slot))

        cursor.execute("DELETE FROM slot_requests WHERE request_id = %s", (request_id,))
        conn.commit()
        flash('Slot request deleted successfully!')
        cursor.close()
        conn.close()
        return redirect(url_for('my_slot_requests'))
    except Exception as e:
        print(f"Error in delete_request route: {e}")
        flash(f"An error occurred: {e}")
        return redirect(url_for('my_slot_requests'))

@app.route('/add_booking', methods=['GET', 'POST'])
@login_required
def add_booking():
    if request.method == 'POST':
        try:
            # Extract form data
            room_id = int(request.form.get('room_id'))  # Convert to integer
            date = request.form.get('date')
            time_slot = request.form.get('time_slot')
            section = request.form.get('section')
            course_code = request.form.get('course_code')
            teacher = current_user.username

            # Debug: Log form data
            print(f"Form data - room_id: {room_id} (type: {type(room_id)}), date: {date}, time_slot: {time_slot}, section: {section}, course_code: {course_code}, teacher: {teacher}")

            # Validate form data
            if not all([room_id, date, time_slot, section, course_code]):
                flash('All fields are required.')
                return redirect(url_for('add_booking'))

            # Validate section and course code
            valid_sections = ['A', 'B', 'C', 'D', 'E']
            valid_course_codes = ['BITMA401', 'BCSDA402', 'BCSDB403', 'BCSSE404', 'BGPEK405', 'BITBE406']
            if section not in valid_sections or course_code not in valid_course_codes:
                flash('Invalid section or course code selected.')
                return redirect(url_for('add_booking'))

            # Parse the booking date and time slot
            try:
                booking_date = datetime.strptime(date, '%Y-%m-%d').date()
                time_slot_parts = time_slot.split('-')
                start_time_str = time_slot_parts[0].strip()  # e.g., '08:30'
                start_time = datetime.strptime(start_time_str, '%H:%M').time()
            except ValueError as ve:
                print(f"Value error in add_booking route: {ve}")
                flash(f"Invalid date or time format: {ve}")
                return redirect(url_for('add_booking'))

            # Current date and time (real-time)
            current_datetime = datetime.now()  # August 09, 2025, 20:49 IST
            current_date = current_datetime.date()
            current_time = current_datetime.time()

            # Combine booking date and start time for comparison
            booking_datetime = datetime.combine(booking_date, start_time)

            # Validate: Prevent bookings in the past
            if booking_datetime < current_datetime:
                flash('Cannot book a classroom for a past date or time.')
                return redirect(url_for('add_booking'))

            # Database operations
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("USE classroom_management")

            # Debug: Test database connection
            cursor.execute("SELECT 1")
            test_result = cursor.fetchone()
            print(f"Database connection test: {test_result}")

            # Debug: Check all bookings
            cursor.execute("SELECT * FROM bookings")
            all_bookings = cursor.fetchall()
            print(f"All bookings in database: {all_bookings}")

            # Debug: Check existing bookings for the date and time slot
            cursor.execute("SELECT * FROM bookings WHERE DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)", (date, time_slot))
            existing_bookings = cursor.fetchall()
            print(f"Existing bookings for {date} {time_slot}: {existing_bookings}")

            # Debug: Check room mapping
            cursor.execute("SELECT room_id, room_name FROM rooms WHERE room_id = %s", (room_id,))
            room_info = cursor.fetchone()
            print(f"Room info for room_id {room_id}: {room_info}")

            # Debug: Log query parameters
            print(f"Query parameters - room_id: {room_id}, date: {date}, time_slot: {time_slot}")

            # Check for time slot conflict and reservation
            cursor.execute("""
                SELECT booking_id
                FROM bookings
                WHERE room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
            """, (room_id, date, time_slot))
            booking_conflict = cursor.fetchone()

            cursor.execute("""
                SELECT reservation_id
                FROM reservations
                WHERE room_id = %s AND DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
                AND expires_at > NOW()
            """, (room_id, date, time_slot))
            reservation_conflict = cursor.fetchone()

            if booking_conflict or reservation_conflict:
                # If there's a conflict, find available rooms for this date and time slot
                cursor.execute("""
                    SELECT room_id FROM rooms
                    WHERE room_id NOT IN (
                        SELECT room_id FROM bookings
                        WHERE DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
                    )
                    AND room_id NOT IN (
                        SELECT room_id FROM reservations
                        WHERE DATE(date) = DATE(%s) AND TRIM(time_slot) = TRIM(%s)
                        AND expires_at > NOW()
                    )
                """, (date, time_slot, date, time_slot))
                available_room_ids = [row[0] for row in cursor.fetchall()]
                print(f"Available room IDs: {available_room_ids}")
                
                # Fetch available rooms
                available_rooms = []
                if available_room_ids:
                    placeholders = ','.join(['%s'] * len(available_room_ids))
                    query = f"SELECT room_id, room_name FROM rooms WHERE room_id IN ({placeholders})"
                    cursor.execute(query, available_room_ids)
                    available_rooms = cursor.fetchall()
                print(f"Available rooms: {available_rooms}")

                cursor.execute("SELECT room_id, room_name FROM rooms")
                all_rooms = cursor.fetchall()
                time_slots = [
                    '08:30-09:30', '09:30-10:30', '11:00-12:00', '12:00-13:00',
                    '14:00-15:00', '15:00-16:00'
                ]
                sections = ['A', 'B', 'C', 'D', 'E']
                course_codes = ['BITMA401', 'BCSDA402', 'BCSDB403', 'BCSSE404', 'BGPEK405', 'BITBE406']
                flash('This room is already booked or reserved for the selected time slot.')
                cursor.close()
                conn.close()
                print(f"Rendering add_booking.html with show_alert=True, available_rooms={available_rooms}")
                return render_template('add_booking.html', rooms=all_rooms, time_slots=time_slots, sections=sections, course_codes=course_codes, available_rooms=available_rooms, selected_date=date, selected_time_slot=time_slot, show_alert=True)

            # No conflict, proceed to insert the booking
            cursor.execute("""
                INSERT INTO bookings (room_id, date, time_slot, teacher, section, course_code)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (room_id, date, time_slot, teacher, section, course_code))
            conn.commit()
            flash('Booking added successfully!')
            cursor.close()
            conn.close()
            return redirect(url_for('index'))

        except mysql.connector.Error as db_err:
            print(f"Database error in add_booking route: {db_err}")
            flash(f"Database error: {db_err}")
            return render_template('add_booking.html', rooms=[], time_slots=[], sections=[], course_codes=[], available_rooms=None, selected_date=None, selected_time_slot=None, show_alert=False)
        except ValueError as ve:
            print(f"Value error in add_booking route: {ve}")
            flash(f"Invalid date or time format: {ve}")
            return render_template('add_booking.html', rooms=[], time_slots=[], sections=[], course_codes=[], available_rooms=None, selected_date=None, selected_time_slot=None, show_alert=False)
        except Exception as e:
            print(f"Unexpected error in add_booking route: {e}")
            flash(f"An unexpected error occurred: {e}")
            return render_template('add_booking.html', rooms=[], time_slots=[], sections=[], course_codes=[], available_rooms=None, selected_date=None, selected_time_slot=None, show_alert=False)

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")
        cursor.execute("SELECT room_id, room_name FROM rooms")
        rooms = cursor.fetchall()
        time_slots = [
            '08:30-09:30', '09:30-10:30', '11:00-12:00', '12:00-13:00',
            '14:00-15:00', '15:00-16:00'
        ]
        sections = ['A', 'B', 'C', 'D', 'E']
        course_codes = ['BITMA401', 'BCSDA402', 'BCSDB403', 'BCSSE404', 'BGPEK405', 'BITBE406']
        cursor.close()
        conn.close()
        return render_template('add_booking.html', rooms=rooms, time_slots=time_slots, sections=sections, course_codes=course_codes, available_rooms=None, selected_date=None, selected_time_slot=None, show_alert=False)
    except Exception as e:
        print(f"Error fetching rooms: {e}")
        flash(f"An error occurred: {e}")
        return render_template('add_booking.html', rooms=[], time_slots=[], sections=[], course_codes=[], available_rooms=None, selected_date=None, selected_time_slot=None, show_alert=False)

@app.route('/delete_booking/<int:booking_id>')
@login_required
def delete_booking(booking_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("USE classroom_management")
        cursor.execute("SELECT booking_id, teacher FROM bookings WHERE booking_id = %s", (booking_id,))
        booking = cursor.fetchone()
        if not booking:
            flash('Booking not found.')
            cursor.close()
            conn.close()
            return redirect(url_for('index'))
        # Allow deletion if user is admin or the teacher who made the booking
        if current_user.role != 'admin' and current_user.username != booking[1]:
            flash('You do not have permission to delete this booking.')
            cursor.close()
            conn.close()
            return redirect(url_for('index'))
        cursor.execute("DELETE FROM bookings WHERE booking_id = %s", (booking_id,))
        conn.commit()
        flash('Booking deleted successfully!')
        cursor.close()
        conn.close()
        return redirect(url_for('index'))
    except Exception as e:
        print(f"Error in delete_booking route: {e}")
        flash(f"An error occurred: {e}")
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)