import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from db import get_db_connection
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "smartlib-development-secret-key-change-later")

# HOME PAGE
@app.route("/")
def home():
    return render_template("index.html")


# ACCESS PORTAL
@app.route("/access")
def access():
    return render_template("access.html")


# STUDENT LOGIN
@app.route("/student-login", methods=["GET", "POST"])
def student_login():

    if request.method == "POST":

        registration = request.form.get("registration", "").strip()
        password = request.form.get("password", "")

        connection = get_db_connection()

        if connection is None:
            return "Database connection failed."

        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM students WHERE registration_number = %s",
                (registration,)
            )

            student = cursor.fetchone()

            if (
                student
                and student["password_hash"]
                and check_password_hash(student["password_hash"], password)
            ):
                session["student_id"] = student["student_id"]
                session["student_name"] = student["full_name"]
                session["student_registration"] = student["registration_number"]

                return redirect(url_for("student_dashboard"))

            return "Invalid registration number or password."

        finally:
            cursor.close()
            connection.close()

    return render_template("student_login.html")


# LIBRARIAN LOGIN
@app.route("/librarian-login", methods=["GET", "POST"])
def librarian_login():

    if request.method == "POST":

        staff_id = request.form.get("staff_id", "").strip()
        password = request.form.get("password", "")

        connection = get_db_connection()

        if connection is None:
            return "Database connection failed."

        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                """
                SELECT * FROM librarians
                WHERE employee_number = %s
                AND account_status = 'Active'
                """,
                (staff_id,)
            )

            librarian = cursor.fetchone()

            if (
                librarian
                and check_password_hash(
                    librarian["password_hash"], password
                )
            ):
                session["librarian_id"] = librarian["librarian_id"]
                session["librarian_name"] = librarian["full_name"]
                session["librarian_role"] = librarian["role"]

                return redirect(url_for("librarian_dashboard"))

            return "Invalid Staff ID or password."

        finally:
            cursor.close()
            connection.close()

    return render_template("librarian_login.html")


# STUDENT REGISTRATION
@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        fullname = request.form.get("fullname", "").strip()
        registration = request.form.get("registration", "").strip()
        course = request.form.get("course", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if password != confirm_password:
            return "Passwords do not match. Please go back and try again."

        if len(password) < 8:
            return "Password must contain at least 8 characters."

        password_hash = generate_password_hash(password)

        connection = get_db_connection()

        if connection is None:
            return "Database connection failed."

        cursor = connection.cursor()

        try:
            sql = """
                INSERT INTO students
                (full_name, registration_number, course, email,
                 phone, password_hash)
                VALUES (%s, %s, %s, %s, %s, %s)
            """

            values = (
                fullname,
                registration,
                course,
                email,
                phone,
                password_hash
            )

            cursor.execute(sql, values)
            connection.commit()

            new_student_id = cursor.lastrowid

            session["student_id"] = new_student_id
            session["student_name"] = fullname
            session["student_registration"] = registration

            return redirect(url_for("student_dashboard"))

        except Exception as e:
            connection.rollback()
            return f"Registration failed: {e}"

        finally:
            cursor.close()
            connection.close()

    return render_template("register.html")



# STUDENT DASHBOARD
@app.route("/student-dashboard")
def student_dashboard():

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:

        student_id = session["student_id"]

        # MY CURRENTLY BORROWED BOOKS
        cursor.execute("""
            SELECT COUNT(*) AS borrowed_count
            FROM borrowing
            WHERE student_id = %s
            AND return_date IS NULL
        """, (student_id,))

        borrowed_count = cursor.fetchone()["borrowed_count"]

        # BOOKS DUE SOON
        cursor.execute("""
            SELECT COUNT(*) AS due_soon_count
            FROM borrowing
            WHERE student_id = %s
            AND return_date IS NULL
            AND due_date BETWEEN CURDATE()
            AND DATE_ADD(CURDATE(), INTERVAL 3 DAY)
        """, (student_id,))

        due_soon_count = cursor.fetchone()["due_soon_count"]

        # MY ACTIVE RESERVATIONS
        cursor.execute("""
            SELECT COUNT(*) AS reservation_count
            FROM reservations
            WHERE student_id = %s
            AND reservation_status IN ('Pending', 'Ready for Collection')
        """, (student_id,))

        reservation_count = cursor.fetchone()["reservation_count"]

        # MY OUTSTANDING FINES
        cursor.execute("""
            SELECT COALESCE(SUM(fine_amount), 0) AS outstanding_fines
            FROM fines
            WHERE student_id = %s
            AND payment_status = 'Unpaid'
        """, (student_id,))

        outstanding_fines = cursor.fetchone()["outstanding_fines"]

        # STUDENT NOTIFICATIONS
        cursor.execute("""
            SELECT *
            FROM notifications
            WHERE student_id = %s
            ORDER BY date_sent DESC
        """, (student_id,))

        notifications = cursor.fetchall()

        # COUNT UNREAD NOTIFICATIONS
        unread_count = sum(
            1 for notification in notifications
            if not notification["is_read"]
        )

        return render_template(
            "student_dashboard.html",
            borrowed_count=borrowed_count,
            due_soon_count=due_soon_count,
            reservation_count=reservation_count,
            outstanding_fines=outstanding_fines,
            notifications=notifications,
            unread_count=unread_count
        )

    finally:
        cursor.close()
        connection.close()



# BOOKS PAGE
@app.route("/books")
def books():

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                books.*,
                digital_resources.resource_id AS digital_resource_id
            FROM books
            LEFT JOIN digital_resources
                ON books.book_id = digital_resources.book_id
            ORDER BY books.title ASC
        """)

        books = cursor.fetchall()

        return render_template(
            "books.html",
            books=books
        )

    finally:
        cursor.close()
        connection.close()


# BOOK DETAILS
@app.route("/book-details/<int:book_id>")
def book_details(book_id):

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT *
            FROM books
            WHERE book_id = %s
        """, (book_id,))

        book = cursor.fetchone()

        if book is None:
            return "Book not found", 404

        # DETERMINE BOOK AVAILABILITY
        if book["available_copies"] > 0:
            book["status"] = "Available"
        else:
            book["status"] = "Borrowed"

        return render_template(
            "book_details.html",
            book=book
        )

    finally:
        cursor.close()
        connection.close()



# STUDENT BORROWING PAGE
@app.route("/borrowing")
def borrowing():

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:

        student_id = session["student_id"]

        cursor.execute("""
            SELECT
                borrowing.borrowing_id,
                borrowing.borrow_date,
                borrowing.due_date,
                borrowing.return_date,
                borrowing.borrowing_status,
                books.title,
                books.author,
                books.isbn
            FROM borrowing
            JOIN books
                ON borrowing.book_id = books.book_id
            WHERE borrowing.student_id = %s
            ORDER BY borrowing.borrow_date DESC
        """, (student_id,))

        borrowings = cursor.fetchall()

        for record in borrowings:

            if record["return_date"] is not None:
                record["display_status"] = "Returned"

            elif record["due_date"] < __import__("datetime").date.today():
                record["display_status"] = "Overdue"

            else:
                record["display_status"] = "Borrowed"

        return render_template(
            "borrowing.html",
            borrowings=borrowings
        )

    finally:
        cursor.close()
        connection.close()




# STUDENT RESERVATIONS PAGE
@app.route("/reservations")
def reservations():

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:

        student_id = session["student_id"]

        cursor.execute("""
            SELECT
                reservations.reservation_id,
                reservations.reservation_date,
                reservations.collection_date,
                reservations.reservation_status,
                books.title,
                books.author,
                books.isbn
            FROM reservations
            JOIN books
                ON reservations.book_id = books.book_id
            WHERE reservations.student_id = %s
            ORDER BY reservations.reservation_date DESC
        """, (student_id,))

        reservation_records = cursor.fetchall()

        return render_template(
            "reservations.html",
            reservations=reservation_records
        )

    finally:
        cursor.close()
        connection.close()



# STUDENT NOTIFICATIONS
@app.route("/notifications")
def notifications():

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        student_id = session["student_id"]

        cursor.execute("""
            SELECT *
            FROM notifications
            WHERE student_id = %s
            ORDER BY date_sent DESC
        """, (student_id,))

        notification_records = cursor.fetchall()

        cursor.execute("""
            SELECT
                COUNT(*) AS total_notifications,
                COALESCE(SUM(notification_type = 'Borrowing'), 0)
                    AS borrowing_notifications,
                COALESCE(SUM(notification_type = 'Overdue'), 0)
                    AS overdue_notifications
            FROM notifications
            WHERE student_id = %s
        """, (student_id,))

        stats = cursor.fetchone()

        return render_template(
            "notifications.html",
            notifications=notification_records,
            total_notifications=stats["total_notifications"],
            borrowing_notifications=stats["borrowing_notifications"],
            overdue_notifications=stats["overdue_notifications"]
        )

    finally:
        cursor.close()
        connection.close()


# MARK ALL STUDENT NOTIFICATIONS AS READ
@app.route("/mark-all-notifications-read", methods=["POST"])
def mark_all_notifications_read():

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE notifications
            SET is_read = TRUE
            WHERE student_id = %s
        """, (session["student_id"],))

        connection.commit()

        return redirect(url_for("notifications"))

    except Exception as e:
        connection.rollback()
        return f"Could not update notifications. Details: {e}"

    finally:
        cursor.close()
        connection.close()


# DIGITAL LIBRARY PAGE
@app.route("/digital-library")
def digital_library():
    return render_template("digital_library.html")



# LIBRARIAN DASHBOARD
@app.route("/librarian-dashboard")
def librarian_dashboard():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:

        # TOTAL BOOKS
        cursor.execute("""
            SELECT COUNT(*) AS total_books
            FROM books
        """)
        total_books = cursor.fetchone()["total_books"]

        # REGISTERED STUDENTS
        cursor.execute("""
            SELECT COUNT(*) AS total_students
            FROM students
        """)
        total_students = cursor.fetchone()["total_students"]

        # CURRENTLY BORROWED BOOKS
        cursor.execute("""
            SELECT COUNT(*) AS borrowed_books
            FROM borrowing
            WHERE return_date IS NULL
        """)
        borrowed_books = cursor.fetchone()["borrowed_books"]

        # OVERDUE BOOKS
        cursor.execute("""
            SELECT COUNT(*) AS overdue_books
            FROM borrowing
            WHERE return_date IS NULL
            AND due_date < CURDATE()
        """)
        overdue_books = cursor.fetchone()["overdue_books"]

        return render_template(
            "librarian_dashboard.html",
            total_books=total_books,
            total_students=total_students,
            borrowed_books=borrowed_books,
            overdue_books=overdue_books
        )

    finally:
        cursor.close()
        connection.close()


# MANAGE BOOKS
@app.route("/manage-books")
def manage_books():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT * FROM books ORDER BY book_id DESC"
        )

        books = cursor.fetchall()

        total_books = sum(book["total_copies"] for book in books)
        available_books = sum(book["available_copies"] for book in books)
        borrowed_books = total_books - available_books

        return render_template(
            "manage_books.html",
            books=books,
            total_books=total_books,
            available_books=available_books,
            borrowed_books=borrowed_books
        )

    finally:
        cursor.close()
        connection.close()



# ADD BOOK
@app.route("/add-book", methods=["POST"])
def add_book():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    category = request.form.get("category", "").strip()
    isbn = request.form.get("isbn", "").strip()
    status = request.form.get("status", "Available")

    if not all([title, author, category, isbn]):
        return "Please complete all book details."

    if status not in ["Available", "Borrowed"]:
        return "Invalid book status."

    total_copies = 1
    available_copies = 1 if status == "Available" else 0

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        # ADD THE BOOK
        cursor.execute(
            """
            INSERT INTO books
            (title, author, category, isbn, total_copies, available_copies)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                title,
                author,
                category,
                isbn,
                total_copies,
                available_copies
            )
        )

        # NOTIFY ALL REGISTERED STUDENTS
        cursor.execute(
            """
            INSERT INTO notifications
            (student_id, notification_title, notification_message,
             notification_type, is_read)
            SELECT
                student_id,
                %s,
                %s,
                'General',
                0
            FROM students
            """,
            (
                "New Book Available",
                f"A new book, '{title}' by {author}, has been added to the library catalogue."
            )
        )

        connection.commit()

        return redirect(url_for("manage_books"))

    except Exception as e:
        connection.rollback()
        return f"Book could not be added: {e}"

    finally:
        cursor.close()
        connection.close()


# UPDATE BOOK
@app.route("/update-book", methods=["POST"])
def update_book():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    book_id = request.form.get("book_id")
    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    category = request.form.get("category", "").strip()
    isbn = request.form.get("isbn", "").strip()
    status = request.form.get("status", "Available")

    if not all([book_id, title, author, category, isbn]):
        return "Please complete all book details."

    if status not in ["Available", "Borrowed"]:
        return "Invalid book status."

    available_copies = 1 if status == "Available" else 0

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE books
            SET title = %s,
                author = %s,
                category = %s,
                isbn = %s,
                available_copies = %s
            WHERE book_id = %s
            """,
            (
                title,
                author,
                category,
                isbn,
                available_copies,
                book_id
            )
        )

        connection.commit()

        return redirect(url_for("manage_books"))

    except Exception as e:
        connection.rollback()
        return f"Book could not be updated: {e}"

    finally:
        cursor.close()
        connection.close()


# DELETE BOOK
@app.route("/delete-book/<int:book_id>", methods=["POST"])
def delete_book(book_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM books WHERE book_id = %s",
            (book_id,)
        )

        connection.commit()

        return redirect(url_for("manage_books"))

    except Exception as e:
        connection.rollback()
        return f"Book could not be deleted: {e}"

    finally:
        cursor.close()
        connection.close()


# MANAGE STUDENTS
@app.route("/manage-students")
def manage_students():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT * FROM students ORDER BY student_id DESC"
        )

        students = cursor.fetchall()

        total_students = len(students)

        active_students = sum(
            1 for student in students
            if student["membership_status"] == "Active"
        )

        inactive_students = total_students - active_students

        return render_template(
            "manage_students.html",
            students=students,
            total_students=total_students,
            active_students=active_students,
            inactive_students=inactive_students
        )

    finally:
        cursor.close()
        connection.close()


# ADD STUDENT
@app.route("/add-student", methods=["POST"])
def add_student():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    full_name = request.form.get("full_name", "").strip()
    registration_number = request.form.get("registration_number", "").strip()
    course = request.form.get("course", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    membership_status = request.form.get("membership_status", "Active")

    if not all([full_name, registration_number, course, email]):
        return "Please complete all required student details."

    if membership_status not in ["Active", "Inactive"]:
        return "Invalid membership status."

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO students
            (full_name, registration_number, course, email,
             phone, membership_status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                full_name,
                registration_number,
                course,
                email,
                phone,
                membership_status
            )
        )

        connection.commit()

        return redirect(url_for("manage_students"))

    except Exception as e:
        connection.rollback()
        return f"Student could not be added: {e}"

    finally:
        cursor.close()
        connection.close()


# UPDATE STUDENT
@app.route("/update-student", methods=["POST"])
def update_student():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    student_id = request.form.get("student_id")
    full_name = request.form.get("full_name", "").strip()
    registration_number = request.form.get("registration_number", "").strip()
    course = request.form.get("course", "").strip()
    email = request.form.get("email", "").strip()
    phone = request.form.get("phone", "").strip()
    membership_status = request.form.get("membership_status", "Active")

    if not all([student_id, full_name, registration_number, course, email]):
        return "Please complete all required student details."

    if membership_status not in ["Active", "Inactive"]:
        return "Invalid membership status."

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE students
            SET full_name = %s,
                registration_number = %s,
                course = %s,
                email = %s,
                phone = %s,
                membership_status = %s
            WHERE student_id = %s
            """,
            (
                full_name,
                registration_number,
                course,
                email,
                phone,
                membership_status,
                student_id
            )
        )

        connection.commit()

        return redirect(url_for("manage_students"))

    except Exception as e:
        connection.rollback()
        return f"Student could not be updated: {e}"

    finally:
        cursor.close()
        connection.close()


# DELETE STUDENT
@app.route("/delete-student/<int:student_id>", methods=["POST"])
def delete_student(student_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute(
            "DELETE FROM students WHERE student_id = %s",
            (student_id,)
        )

        connection.commit()

        return redirect(url_for("manage_students"))

    except Exception as e:
        connection.rollback()
        return (
            "Student could not be deleted. The student may have borrowing "
            "or reservation records linked to their account. Details: "
            f"{e}"
        )

    finally:
        cursor.close()
        connection.close()



# MANAGE BORROWING
@app.route("/manage-borrowing")
def manage_borrowing():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        # GET BORROWING RECORDS
        cursor.execute(
            """
            SELECT
                borrowing.borrowing_id,
                borrowing.borrow_date,
                borrowing.due_date,
                borrowing.return_date,
                students.full_name AS student_name,
                students.registration_number,
                books.title AS book_title,

                CASE
                    WHEN borrowing.return_date IS NOT NULL
                        THEN 'Returned'
                    WHEN borrowing.due_date < CURDATE()
                        THEN 'Overdue'
                    ELSE 'Borrowed'
                END AS current_status

            FROM borrowing

            INNER JOIN students
                ON borrowing.student_id = students.student_id

            INNER JOIN books
                ON borrowing.book_id = books.book_id

            ORDER BY borrowing.borrowing_id DESC
            """
        )

        borrowings = cursor.fetchall()

        # GET STUDENTS
        cursor.execute(
            """
            SELECT student_id, full_name, registration_number
            FROM students
            WHERE membership_status = 'Active'
            ORDER BY full_name ASC
            """
        )

        students = cursor.fetchall()

        # GET AVAILABLE BOOKS
        cursor.execute(
            """
            SELECT book_id, title, available_copies
            FROM books
            WHERE available_copies > 0
            ORDER BY title ASC
            """
        )

        books = cursor.fetchall()

        # CALCULATE SUMMARY COUNTS
        total_records = len(borrowings)

        borrowed_count = sum(
            1 for record in borrowings
            if record["current_status"] == "Borrowed"
        )

        overdue_count = sum(
            1 for record in borrowings
            if record["current_status"] == "Overdue"
        )

        returned_count = sum(
            1 for record in borrowings
            if record["current_status"] == "Returned"
        )

        return render_template(
            "manage_borrowing.html",
            borrowings=borrowings,
            students=students,
            books=books,
            total_records=total_records,
            borrowed_count=borrowed_count,
            overdue_count=overdue_count,
            returned_count=returned_count
        )

    finally:
        cursor.close()
        connection.close()



# ADD BORROWING
@app.route("/add-borrowing", methods=["POST"])
def add_borrowing():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    student_id = request.form.get("student_id")
    book_id = request.form.get("book_id")
    borrow_date = request.form.get("borrow_date")

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s
            AND membership_status = 'Active'
        """, (student_id,))

        student = cursor.fetchone()

        if not student:
            connection.rollback()
            return "The selected student is not active."

        cursor.execute("""
            SELECT book_id, available_copies
            FROM books
            WHERE book_id = %s
            FOR UPDATE
        """, (book_id,))

        book = cursor.fetchone()

        if not book or book["available_copies"] <= 0:
            connection.rollback()
            return "This book is currently unavailable."

        from datetime import date, timedelta

        try:
            borrow_date_value = date.fromisoformat(borrow_date)
        except (ValueError, TypeError):
            connection.rollback()
            return "Please provide a valid borrowing date."

        # Automatically calculate the due date after exactly 14 days
        due_date_value = borrow_date_value + timedelta(days=14)

        cursor.execute("""
            INSERT INTO borrowing
            (student_id, book_id, borrow_date, due_date, borrowing_status)
            VALUES (%s, %s, %s, %s, 'Borrowed')
        """, (
            student_id,
            book_id,
            borrow_date_value,
            due_date_value
        ))

        cursor.execute("""
            UPDATE books
            SET available_copies = available_copies - 1
            WHERE book_id = %s
        """, (book_id,))

        connection.commit()

        return redirect(url_for("manage_borrowing"))

    except Exception as e:
        connection.rollback()
        return f"Could not record borrowing. Details: {e}"

    finally:
        cursor.close()
        connection.close()




# RETURN BOOK
@app.route("/return-book/<int:borrowing_id>", methods=["POST"])
def return_book(borrowing_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        cursor.execute(
            """
            SELECT borrowing_id, book_id, return_date, due_date, student_id
            FROM borrowing
            WHERE borrowing_id = %s
            FOR UPDATE
            """,
            (borrowing_id,)
        )

        borrowing = cursor.fetchone()

        if not borrowing:
            connection.rollback()
            return "Borrowing record not found."

        if borrowing["return_date"] is not None:
            connection.rollback()
            return "This book has already been returned."

        # Calculate overdue days using the database date
        cursor.execute(
            """
            SELECT GREATEST(DATEDIFF(CURDATE(), %s), 0) AS days_overdue
            """,
            (borrowing["due_date"],)
        )

        result = cursor.fetchone()
        days_overdue = result["days_overdue"]

        # Update borrowing record
        cursor.execute(
            """
            UPDATE borrowing
            SET return_date = CURDATE(),
                borrowing_status = 'Returned'
            WHERE borrowing_id = %s
            """,
            (borrowing_id,)
        )

        # Restore available book copy
        cursor.execute(
            """
            UPDATE books
            SET available_copies = LEAST(available_copies + 1, total_copies)
            WHERE book_id = %s
            """,
            (borrowing["book_id"],)
        )

        # Record fine if the book was returned late
        if days_overdue > 0:

            fine_rate = 20
            fine_amount = days_overdue * fine_rate

            cursor.execute(
                """
                INSERT INTO fines
                (borrowing_id, student_id, fine_amount,
                 days_overdue, payment_status)
                VALUES (%s, %s, %s, %s, 'Unpaid')
                """,
                (
                    borrowing_id,
                    borrowing["student_id"],
                    fine_amount,
                    days_overdue
                )
            )

        connection.commit()

        return redirect(url_for("manage_borrowing"))

    except Exception as e:
        connection.rollback()
        return f"Could not return book. Details: {e}"

    finally:
        cursor.close()
        connection.close()




# MANAGE RESERVATIONS
@app.route("/manage-reservations")
def manage_reservations():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        # GET RESERVATION RECORDS
        cursor.execute(
            """
            SELECT
                reservations.reservation_id,
                reservations.reservation_date,
                reservations.collection_date,
                reservations.reservation_status,
                students.full_name AS student_name,
                students.registration_number,
                books.title AS book_title

            FROM reservations

            INNER JOIN students
                ON reservations.student_id = students.student_id

            INNER JOIN books
                ON reservations.book_id = books.book_id

            ORDER BY reservations.reservation_id DESC
            """
        )

        reservations = cursor.fetchall()

        # GET ACTIVE STUDENTS
        cursor.execute(
            """
            SELECT student_id, full_name, registration_number
            FROM students
            WHERE membership_status = 'Active'
            ORDER BY full_name ASC
            """
        )

        students = cursor.fetchall()

        # GET BOOKS WITH AVAILABLE COPIES
        cursor.execute(
            """
            SELECT book_id, title, available_copies
            FROM books
            WHERE available_copies > 0
            ORDER BY title ASC
            """
        )

        books = cursor.fetchall()

        # CALCULATE RESERVATION COUNTS
        total_reservations = len(reservations)

        pending_reservations = sum(
            1 for record in reservations
            if record["reservation_status"] == "Pending"
        )

        ready_reservations = sum(
            1 for record in reservations
            if record["reservation_status"] == "Ready for Collection"
        )

        completed_reservations = sum(
            1 for record in reservations
            if record["reservation_status"] == "Completed"
        )

        return render_template(
            "manage_reservations.html",
            reservations=reservations,
            students=students,
            books=books,
            total_reservations=total_reservations,
            pending_reservations=pending_reservations,
            ready_reservations=ready_reservations,
            completed_reservations=completed_reservations
        )

    finally:
        cursor.close()
        connection.close()




# MANAGE DIGITAL RESOURCES
@app.route("/manage-digital-resources")
def manage_digital_resources():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        # GET ALL DIGITAL RESOURCES
        cursor.execute(
            """
            SELECT *
            FROM digital_resources
            ORDER BY resource_id DESC
            """
        )

        resources = cursor.fetchall()

        # CALCULATE RESOURCE COUNTS
        total_resources = len(resources)

        ebook_count = sum(
            1 for resource in resources
            if resource["category"] == "E-Book"
        )

        journal_count = sum(
            1 for resource in resources
            if resource["category"] == "Journal"
        )

        paper_count = sum(
            1 for resource in resources
            if resource["category"] == "Research Paper"
        )

        return render_template(
            "manage_digital_resource.html",
            resources=resources,
            total_resources=total_resources,
            ebook_count=ebook_count,
            journal_count=journal_count,
            paper_count=paper_count
        )

    finally:
        cursor.close()
        connection.close()

# ADD DIGITAL RESOURCE
@app.route("/add-digital-resource", methods=["POST"])
def add_digital_resource():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    category = request.form.get("category", "")
    publication_year = request.form.get("publication_year", "")
    file_format = request.form.get("file_format", "")
    resource_url = request.form.get("resource_url", "").strip()

    allowed_categories = [
        "E-Book",
        "Journal",
        "Research Paper",
        "Study Notes"
    ]

    allowed_formats = ["PDF", "EPUB", "DOCX", "PPTX"]

    if not all([title, author, category, publication_year, file_format]):
        flash("Please complete all required fields.")
        return redirect(url_for("manage_digital_resources"))

    if category not in allowed_categories or file_format not in allowed_formats:
        flash("Invalid resource category or file format.")
        return redirect(url_for("manage_digital_resources"))

    try:
        publication_year = int(publication_year)

        if publication_year < 1900 or publication_year > 2100:
            raise ValueError

    except ValueError:
        flash("Please enter a valid publication year.")
        return redirect(url_for("manage_digital_resources"))

    if resource_url:
        from urllib.parse import urlparse

        parsed_url = urlparse(resource_url)

        if parsed_url.scheme not in ["http", "https"] or not parsed_url.netloc:
            flash("Please enter a valid HTTP or HTTPS resource link.")
            return redirect(url_for("manage_digital_resources"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO digital_resources (
                title,
                author,
                category,
                publication_year,
                file_format,
                resource_url
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                title,
                author,
                category,
                publication_year,
                file_format,
                resource_url or None
            )
        )

        connection.commit()

        flash("Digital resource added successfully.")

    except Exception as e:
        connection.rollback()
        print("Digital resource error:", e)
        flash("Unable to add digital resource.")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("manage_digital_resources"))

# UPDATE DIGITAL RESOURCE
@app.route("/update-digital-resource/<int:resource_id>", methods=["POST"])
def update_digital_resource(resource_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    title = request.form.get("title", "").strip()
    author = request.form.get("author", "").strip()
    category = request.form.get("category", "")
    publication_year = request.form.get("publication_year", "")
    file_format = request.form.get("file_format", "")
    resource_url = request.form.get("resource_url", "").strip()

    allowed_categories = [
        "E-Book",
        "Journal",
        "Research Paper",
        "Study Notes"
    ]

    allowed_formats = ["PDF", "EPUB", "DOCX", "PPTX"]

    if not all([title, author, category, publication_year, file_format]):
        flash("Please complete all required fields.")
        return redirect(url_for("manage_digital_resources"))

    if category not in allowed_categories or file_format not in allowed_formats:
        flash("Invalid resource category or file format.")
        return redirect(url_for("manage_digital_resources"))

    try:
        publication_year = int(publication_year)

        if publication_year < 1900 or publication_year > 2100:
            raise ValueError

    except ValueError:
        flash("Please enter a valid publication year.")
        return redirect(url_for("manage_digital_resources"))

    if resource_url:
        from urllib.parse import urlparse

        parsed_url = urlparse(resource_url)

        if parsed_url.scheme not in ["http", "https"] or not parsed_url.netloc:
            flash("Please enter a valid HTTP or HTTPS resource link.")
            return redirect(url_for("manage_digital_resources"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE digital_resources
            SET
                title = %s,
                author = %s,
                category = %s,
                publication_year = %s,
                file_format = %s,
                resource_url = %s
            WHERE resource_id = %s
            """,
            (
                title,
                author,
                category,
                publication_year,
                file_format,
                resource_url or None,
                resource_id
            )
        )

        if cursor.rowcount == 0:
            flash("Resource not found or no changes were made.")
        else:
            flash("Digital resource updated successfully.")

        connection.commit()

    except Exception as e:
        connection.rollback()
        print("Digital resource update error:", e)
        flash("Unable to update digital resource.")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("manage_digital_resources"))

# DELETE DIGITAL RESOURCE
@app.route("/delete-digital-resource/<int:resource_id>", methods=["POST"])
def delete_digital_resource(resource_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            DELETE FROM digital_resources
            WHERE resource_id = %s
            """,
            (resource_id,)
        )

        connection.commit()

        if cursor.rowcount > 0:
            flash("Digital resource deleted successfully.")
        else:
            flash("Digital resource not found.")

    except Exception as e:
        connection.rollback()
        print("Digital resource deletion error:", e)
        flash("Unable to delete digital resource.")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("manage_digital_resources"))



# ADD NEW RESERVATION
@app.route("/add-reservation", methods=["POST"])
def add_reservation():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    student_id = request.form.get("student_id")
    book_id = request.form.get("book_id")
    reservation_date = request.form.get("reservation_date")
    collection_date = request.form.get("collection_date")

    if not student_id or not book_id or not reservation_date or not collection_date:
        flash("Please complete all reservation fields.")
        return redirect(url_for("manage_reservations"))

    if collection_date < reservation_date:
        flash("Collection date cannot be before the reservation date.")
        return redirect(url_for("manage_reservations"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        # CHECK THAT THE STUDENT IS ACTIVE
        cursor.execute(
            """
            SELECT student_id
            FROM students
            WHERE student_id = %s
            AND membership_status = 'Active'
            """,
            (student_id,)
        )

        student = cursor.fetchone()

        if not student:
            flash("The selected student is not active or does not exist.")
            return redirect(url_for("manage_reservations"))

        # CHECK THAT THE BOOK EXISTS
        cursor.execute(
            """
            SELECT book_id
            FROM books
            WHERE book_id = %s
            """,
            (book_id,)
        )

        book = cursor.fetchone()

        if not book:
            flash("The selected book does not exist.")
            return redirect(url_for("manage_reservations"))

        # PREVENT DUPLICATE ACTIVE RESERVATIONS
        cursor.execute(
            """
            SELECT reservation_id
            FROM reservations
            WHERE student_id = %s
            AND book_id = %s
            AND reservation_status IN ('Pending', 'Ready for Collection')
            """,
            (student_id, book_id)
        )

        existing_reservation = cursor.fetchone()

        if existing_reservation:
            flash("This student already has an active reservation for this book.")
            return redirect(url_for("manage_reservations"))

        # SAVE THE RESERVATION
        cursor.execute(
            """
            INSERT INTO reservations (
                student_id,
                book_id,
                reservation_date,
                collection_date,
                reservation_status
            )
            VALUES (%s, %s, %s, %s, 'Pending')
            """,
            (
                student_id,
                book_id,
                reservation_date,
                collection_date
            )
        )

        connection.commit()

        flash("Reservation registered successfully.")

    except Exception as e:
        connection.rollback()
        print("Reservation error:", e)
        flash("Unable to register the reservation. Please try again.")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("manage_reservations"))


# UPDATE RESERVATION STATUS
@app.route("/update-reservation-status/<int:reservation_id>", methods=["POST"])
def update_reservation_status(reservation_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    new_status = request.form.get("status")

    allowed_statuses = [
        "Ready for Collection",
        "Cancelled",
        "Completed"
    ]

    if new_status not in allowed_statuses:
        flash("Invalid reservation status.")
        return redirect(url_for("manage_reservations"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        # FIND THE RESERVATION
        cursor.execute(
            """
            SELECT reservation_status, student_id
            FROM reservations
            WHERE reservation_id = %s
            FOR UPDATE
            """,
            (reservation_id,)
        )

        reservation = cursor.fetchone()

        if not reservation:
            connection.rollback()
            flash("Reservation not found.")
            return redirect(url_for("manage_reservations"))

        current_status = reservation["reservation_status"]
        student_id = reservation["student_id"]

        # CHECK VALID STATUS TRANSITIONS
        valid_transition = (
            (current_status == "Pending" and new_status in [
                "Ready for Collection",
                "Cancelled"
            ])
            or
            (current_status == "Ready for Collection" and new_status == "Completed")
        )

        if not valid_transition:
            connection.rollback()
            flash("This reservation cannot be updated to the selected status.")
            return redirect(url_for("manage_reservations"))

        # UPDATE RESERVATION
        cursor.execute(
            """
            UPDATE reservations
            SET reservation_status = %s
            WHERE reservation_id = %s
            """,
            (new_status, reservation_id)
        )

        # NOTIFY STUDENT WHEN BOOK IS READY
        if new_status == "Ready for Collection":

            cursor.execute(
                """
                INSERT INTO notifications
                (student_id, notification_title, notification_message,
                 notification_type, is_read)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    student_id,
                    "Reservation Ready for Collection",
                    "Your reserved book is ready for collection. Please visit the library.",
                    "Reservation",
                    0
                )
            )

        connection.commit()

        flash("Reservation status updated successfully.")

    except Exception as e:
        connection.rollback()
        print("Reservation update error:", e)
        flash("Unable to update the reservation status.")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("manage_reservations"))


# LIBRARY REPORTS
@app.route("/library-reports")
def library_reports():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    period = request.args.get("period", "monthly")

    if period not in ["weekly", "monthly", "yearly"]:
        period = "monthly"

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:

        # TOTAL BOOK COPIES
        cursor.execute(
            """
            SELECT
                COALESCE(SUM(total_copies), 0) AS total_books,
                COALESCE(SUM(available_copies), 0) AS total_available
            FROM books
            """
        )

        book_stats = cursor.fetchone()

        total_books = book_stats["total_books"]
        total_available = book_stats["total_available"]

        # REGISTERED STUDENTS
        cursor.execute(
            """
            SELECT COUNT(*) AS total_students
            FROM students
            """
        )

        total_students = cursor.fetchone()["total_students"]

        # CURRENTLY BORROWED BOOKS
        cursor.execute(
            """
            SELECT COUNT(*) AS total_borrowed
            FROM borrowing
            WHERE return_date IS NULL
            """
        )

        total_borrowed = cursor.fetchone()["total_borrowed"]

        # BOOKS ISSUED DURING SELECTED PERIOD
        cursor.execute(
            """
            SELECT COUNT(*) AS books_issued
            FROM borrowing
            WHERE borrow_date >=
                CASE
                    WHEN %s = 'weekly'
                        THEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)
                    WHEN %s = 'yearly'
                        THEN MAKEDATE(YEAR(CURDATE()), 1)
                    ELSE DATE_FORMAT(CURDATE(), '%%Y-%%m-01')
                END
            AND borrow_date <= CURDATE()
            """,
            (period, period)
        )

        books_issued = cursor.fetchone()["books_issued"]

        # BOOKS RETURNED DURING SELECTED PERIOD
        cursor.execute(
            """
            SELECT COUNT(*) AS books_returned
            FROM borrowing
            WHERE return_date IS NOT NULL
            AND return_date >=
                CASE
                    WHEN %s = 'weekly'
                        THEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)
                    WHEN %s = 'yearly'
                        THEN MAKEDATE(YEAR(CURDATE()), 1)
                    ELSE DATE_FORMAT(CURDATE(), '%%Y-%%m-01')
                END
            AND return_date <= CURDATE()
            """,
            (period, period)
        )

        books_returned = cursor.fetchone()["books_returned"]

        # CURRENT OVERDUE BOOKS
        cursor.execute(
            """
            SELECT COUNT(*) AS overdue_books
            FROM borrowing
            WHERE return_date IS NULL
            AND due_date < CURDATE()
            """
        )

        overdue_books = cursor.fetchone()["overdue_books"]

        # RESERVATIONS DURING SELECTED PERIOD
        cursor.execute(
            """
            SELECT COUNT(*) AS total_reservations
            FROM reservations
            WHERE reservation_date >=
                CASE
                    WHEN %s = 'weekly'
                        THEN DATE_SUB(CURDATE(), INTERVAL WEEKDAY(CURDATE()) DAY)
                    WHEN %s = 'yearly'
                        THEN MAKEDATE(YEAR(CURDATE()), 1)
                    ELSE DATE_FORMAT(CURDATE(), '%%Y-%%m-01')
                END
            AND reservation_date <= CURDATE()
            """,
            (period, period)
        )

        total_reservations = cursor.fetchone()["total_reservations"]

        # DIGITAL RESOURCE STATISTICS
        cursor.execute(
            """
            SELECT
                COUNT(*) AS total_digital_resources,

                COALESCE(SUM(category = 'E-Book'), 0) AS ebook_count,

                COALESCE(SUM(category = 'Journal'), 0) AS journal_count,

                COALESCE(SUM(category = 'Research Paper'), 0) AS paper_count,

                COALESCE(SUM(category = 'Study Notes'), 0) AS notes_count

            FROM digital_resources
            """
        )

        digital_stats = cursor.fetchone()

        total_digital_resources = digital_stats["total_digital_resources"]
        ebook_count = digital_stats["ebook_count"]
        journal_count = digital_stats["journal_count"]
        paper_count = digital_stats["paper_count"]
        notes_count = digital_stats["notes_count"]

        # CALCULATE ACTIVITY BAR PERCENTAGES
        largest_activity = max(
            books_issued,
            books_returned,
            overdue_books,
            total_reservations,
            1
        )

        issued_percentage = (books_issued / largest_activity) * 100
        returned_percentage = (books_returned / largest_activity) * 100
        overdue_percentage = (overdue_books / largest_activity) * 100
        reservation_percentage = (total_reservations / largest_activity) * 100

        # MONTHLY BORROWING AND RETURN TRENDS
        cursor.execute(
            """
            SELECT
                MONTH(borrow_date) AS month_number,
                COUNT(*) AS monthly_issued,
                SUM(return_date IS NOT NULL) AS monthly_returned

            FROM borrowing

            WHERE YEAR(borrow_date) = YEAR(CURDATE())

            GROUP BY MONTH(borrow_date)

            ORDER BY month_number
            """
        )

        monthly_records = cursor.fetchall()

        month_labels = [
            "January", "February", "March", "April",
            "May", "June", "July", "August",
            "September", "October", "November", "December"
        ]

        monthly_issued = [0] * 12
        monthly_returned = [0] * 12

        for record in monthly_records:

            month_index = record["month_number"] - 1

            monthly_issued[month_index] = record["monthly_issued"]
            monthly_returned[month_index] = record["monthly_returned"]

        # CHART DATA
        chart_data = {
            "books_issued": books_issued,
            "books_returned": books_returned,
            "overdue_books": overdue_books,
            "total_reservations": total_reservations,
            "total_available": total_available,
            "total_borrowed": total_borrowed,
            "month_labels": month_labels,
            "monthly_issued": monthly_issued,
            "monthly_returned": monthly_returned
        }

        return render_template(
            "library_reports.html",

            total_books=total_books,
            total_students=total_students,
            total_borrowed=total_borrowed,
            total_available=total_available,

            books_issued=books_issued,
            books_returned=books_returned,
            overdue_books=overdue_books,
            total_reservations=total_reservations,

            total_digital_resources=total_digital_resources,
            ebook_count=ebook_count,
            journal_count=journal_count,
            paper_count=paper_count,
            notes_count=notes_count,

            issued_percentage=issued_percentage,
            returned_percentage=returned_percentage,
            overdue_percentage=overdue_percentage,
            reservation_percentage=reservation_percentage,

            chart_data=chart_data,
            period=period
        )

    finally:
        cursor.close()
        connection.close()



# STUDENT LOGOUT
@app.route("/student-logout")
def student_logout():

    session.clear()

    return redirect(url_for("student_login"))


# LIBRARIAN LOGOUT
@app.route("/librarian-logout")
def librarian_logout():

    session.pop("librarian_id", None)
    session.pop("librarian_name", None)
    session.pop("librarian_role", None)

    return redirect(url_for("librarian_login"))

# CANCEL STUDENT RESERVATION
@app.route("/cancel-student-reservation/<int:reservation_id>", methods=["POST"])
def cancel_student_reservation(reservation_id):

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:

        student_id = session["student_id"]

        cursor.execute("""
            SELECT reservation_status
            FROM reservations
            WHERE reservation_id = %s
            AND student_id = %s
        """, (reservation_id, student_id))

        reservation = cursor.fetchone()

        if reservation is None:
            return "Reservation not found.", 404

        if reservation["reservation_status"] != "Pending":
            return "Only pending reservations can be cancelled.", 400

        cursor.execute("""
            UPDATE reservations
            SET reservation_status = 'Cancelled'
            WHERE reservation_id = %s
            AND student_id = %s
        """, (reservation_id, student_id))

        connection.commit()

        return redirect(url_for("reservations"))

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()
# DELETE RESERVATION
@app.route("/delete-reservation/<int:reservation_id>", methods=["POST"])
def delete_reservation(reservation_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute("""
            DELETE FROM reservations
            WHERE reservation_id = %s
        """, (reservation_id,))

        connection.commit()

        return redirect(url_for("manage_reservations"))

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()



# COLLECT RESERVATION AND CREATE BORROWING RECORD
@app.route("/collect-reservation/<int:reservation_id>", methods=["POST"])
def collect_reservation(reservation_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        cursor.execute("""
            SELECT student_id, book_id, reservation_status
            FROM reservations
            WHERE reservation_id = %s
            FOR UPDATE
        """, (reservation_id,))

        reservation = cursor.fetchone()

        if reservation is None:
            connection.rollback()
            flash("Reservation not found.", "error")
            return redirect(url_for("manage_reservations"))

        if reservation["reservation_status"] != "Ready for Collection":
            connection.rollback()
            flash("This reservation is not ready for collection.", "error")
            return redirect(url_for("manage_reservations"))

        student_id = reservation["student_id"]
        book_id = reservation["book_id"]

        cursor.execute("""
            SELECT borrowing_id
            FROM borrowing
            WHERE student_id = %s
            AND book_id = %s
            AND return_date IS NULL
        """, (student_id, book_id))

        if cursor.fetchone():
            connection.rollback()
            flash("This student already has an active borrowing record for this book.", "error")
            return redirect(url_for("manage_reservations"))

        cursor.execute("""
            SELECT available_copies
            FROM books
            WHERE book_id = %s
            FOR UPDATE
        """, (book_id,))

        book = cursor.fetchone()

        if book is None or book["available_copies"] < 1:
            connection.rollback()
            flash("This book is currently unavailable.", "error")
            return redirect(url_for("manage_reservations"))

        # Calculate borrowing and due dates
        from datetime import date, timedelta

        borrow_date = date.today()
        due_date = borrow_date + timedelta(days=14)

        cursor.execute("""
            INSERT INTO borrowing (
                student_id,
                book_id,
                borrow_date,
                due_date,
                borrowing_status
            )
            VALUES (%s, %s, %s, %s, 'Borrowed')
        """, (student_id, book_id, borrow_date, due_date))

        cursor.execute("""
            UPDATE books
            SET available_copies = available_copies - 1
            WHERE book_id = %s
            AND available_copies > 0
        """, (book_id,))

        cursor.execute("""
            UPDATE reservations
            SET reservation_status = 'Completed'
            WHERE reservation_id = %s
        """, (reservation_id,))

        connection.commit()

        flash("Book collected successfully. The due date is exactly 14 days after borrowing.", "success")

        return redirect(url_for("manage_reservations"))

    except Exception:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()



# UNDO BOOK RETURN
@app.route("/undo-return/<int:borrowing_id>", methods=["POST"])
def undo_return(borrowing_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        # Find and lock the borrowing record
        cursor.execute("""
            SELECT borrowing_id, book_id, return_date
            FROM borrowing
            WHERE borrowing_id = %s
            FOR UPDATE
        """, (borrowing_id,))

        borrowing = cursor.fetchone()

        if borrowing is None:
            connection.rollback()
            flash("Borrowing record not found.", "error")
            return redirect(url_for("manage_borrowing"))

        if borrowing["return_date"] is None:
            connection.rollback()
            flash("This book has not been marked as returned.", "error")
            return redirect(url_for("manage_borrowing"))

        # Lock the book record
        cursor.execute("""
            SELECT available_copies, total_copies
            FROM books
            WHERE book_id = %s
            FOR UPDATE
        """, (borrowing["book_id"],))

        book = cursor.fetchone()

        if book is None:
            connection.rollback()
            flash("Book record not found.", "error")
            return redirect(url_for("manage_borrowing"))

        if book["available_copies"] < 1:
            connection.rollback()
            flash(
                "Cannot undo this return because no book copies are currently available.",
                "error"
            )
            return redirect(url_for("manage_borrowing"))

        # Restore the borrowing record
        cursor.execute("""
            UPDATE borrowing
            SET return_date = NULL,
                borrowing_status = 'Borrowed'
            WHERE borrowing_id = %s
        """, (borrowing_id,))

        # Reduce available copies
        cursor.execute("""
            UPDATE books
            SET available_copies = available_copies - 1
            WHERE book_id = %s
        """, (borrowing["book_id"],))

        connection.commit()

        flash("Return successfully reversed. The borrowing record is active again.", "success")

        return redirect(url_for("manage_borrowing"))

    except Exception as e:
        connection.rollback()
        return f"Could not undo return. Details: {e}"

    finally:
        cursor.close()
        connection.close()

# DELETE A TEST BORROWING RECORD
@app.route("/delete-borrowing/<int:borrowing_id>", methods=["POST"])
def delete_borrowing(borrowing_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        cursor.execute("""
            SELECT borrowing_id, return_date
            FROM borrowing
            WHERE borrowing_id = %s
            FOR UPDATE
        """, (borrowing_id,))

        borrowing = cursor.fetchone()

        if borrowing is None:
            connection.rollback()
            flash("Borrowing record not found.", "error")
            return redirect(url_for("manage_borrowing"))

        if borrowing["return_date"] is None:
            connection.rollback()
            flash("Only returned test records can be deleted.", "error")
            return redirect(url_for("manage_borrowing"))

        cursor.execute("""
            DELETE FROM borrowing
            WHERE borrowing_id = %s
        """, (borrowing_id,))

        connection.commit()

        flash("Test borrowing record deleted successfully.", "success")

        return redirect(url_for("manage_borrowing"))

    except Exception as e:
        connection.rollback()
        return f"Could not delete borrowing record. Details: {e}"

    finally:
        cursor.close()
        connection.close()

# STUDENT BOOK RESERVATION
@app.route("/student-reserve-book/<int:book_id>", methods=["POST"])
def student_reserve_book(book_id):

    if "student_id" not in session:
        return redirect(url_for("student_login"))

    from datetime import date

    collection_date = request.form.get("collection_date")

    try:
        collection_date_value = date.fromisoformat(collection_date)

        if collection_date_value < date.today():
            flash("Please select today or a future collection date.", "error")
            return redirect(url_for("book_details", book_id=book_id))

    except (ValueError, TypeError):
        flash("Please select a valid collection date.", "error")
        return redirect(url_for("book_details", book_id=book_id))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        student_id = session["student_id"]

        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s
            AND membership_status = 'Active'
        """, (student_id,))

        student = cursor.fetchone()

        if student is None:
            connection.rollback()
            flash("Your student account is not active.", "error")
            return redirect(url_for("book_details", book_id=book_id))

        cursor.execute("""
            SELECT book_id, available_copies
            FROM books
            WHERE book_id = %s
            FOR UPDATE
        """, (book_id,))

        book = cursor.fetchone()

        if book is None:
            connection.rollback()
            return "Book not found.", 404

        if book["available_copies"] <= 0:
            connection.rollback()
            flash("This book is currently unavailable.", "error")
            return redirect(url_for("book_details", book_id=book_id))

        cursor.execute("""
            SELECT reservation_id
            FROM reservations
            WHERE student_id = %s
            AND book_id = %s
            AND reservation_status IN ('Pending', 'Ready for Collection')
        """, (student_id, book_id))

        existing_reservation = cursor.fetchone()

        if existing_reservation:
            connection.rollback()
            flash("You already have an active reservation for this book.", "error")
            return redirect(url_for("book_details", book_id=book_id))

        cursor.execute("""
            INSERT INTO reservations
            (student_id, book_id, reservation_date, collection_date, reservation_status)
            VALUES (%s, %s, CURDATE(), %s, 'Pending')
        """, (student_id, book_id, collection_date_value))

        connection.commit()

        flash("Book reservation submitted successfully!", "success")

        return redirect(url_for("reservations"))

    except Exception as e:
        connection.rollback()
        return f"Could not submit reservation. Details: {e}"

    finally:
        cursor.close()
        connection.close()


# LIBRARIAN ANNOUNCEMENTS
@app.route("/librarian-announcements", methods=["GET", "POST"])
def librarian_announcements():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    if request.method == "POST":

        title = request.form.get("title", "").strip()
        message = request.form.get("message", "").strip()

        if not title or not message:
            flash("Please enter both the announcement title and message.", "error")
            return redirect(url_for("librarian_announcements"))

        connection = get_db_connection()

        if connection is None:
            flash("Database connection failed.", "error")
            return redirect(url_for("librarian_announcements"))

        cursor = connection.cursor()

        try:
            cursor.execute(
                """
                INSERT INTO notifications
                (student_id, notification_title, notification_message,
                 notification_type, is_read)
                SELECT
                    student_id, %s, %s, 'General', 0
                FROM students
                """,
                (title, message)
            )

            students_notified = cursor.rowcount
            connection.commit()

            if students_notified > 0:
                flash(
                    f"Announcement successfully sent to {students_notified} students.",
                    "success"
                )
            else:
                flash("There are no registered students to notify.", "error")

        except Exception as e:
            connection.rollback()
            flash("Could not send announcement. Please try again.", "error")
            print("Announcement Error:", e)

        finally:
            cursor.close()
            connection.close()

        return redirect(url_for("librarian_announcements"))

    return render_template("librarian_announcements.html")


# MANAGE FINES
@app.route("/manage-fines")
def manage_fines():

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                fines.fine_id,
                fines.borrowing_id,
                fines.student_id,
                students.full_name,
                students.registration_number,
                books.title,
                fines.fine_amount,
                fines.days_overdue,
                fines.payment_status,
                fines.date_recorded
            FROM fines
            JOIN students
                ON fines.student_id = students.student_id
            JOIN borrowing
                ON fines.borrowing_id = borrowing.borrowing_id
            JOIN books
                ON borrowing.book_id = books.book_id
            ORDER BY fines.date_recorded DESC
        """)

        fines = cursor.fetchall()

        total_fines = sum(float(f["fine_amount"]) for f in fines)
        unpaid_fines = sum(
            float(f["fine_amount"])
            for f in fines
            if f["payment_status"] == "Unpaid"
        )
        paid_fines = sum(
            float(f["fine_amount"])
            for f in fines
            if f["payment_status"] == "Paid"
        )

        return render_template(
            "manage_fines.html",
            fines=fines,
            total_fines=total_fines,
            unpaid_fines=unpaid_fines,
            paid_fines=paid_fines
        )

    except Exception as e:
        return f"Could not load fines. Details: {e}"

    finally:
        cursor.close()
        connection.close()

# MARK FINE AS PAID
@app.route("/mark-fine-paid/<int:fine_id>", methods=["POST"])
def mark_fine_paid(fine_id):

    if "librarian_id" not in session:
        return redirect(url_for("librarian_login"))

    connection = get_db_connection()

    if connection is None:
        return "Database connection failed."

    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            UPDATE fines
            SET payment_status = 'Paid'
            WHERE fine_id = %s
            AND payment_status = 'Unpaid'
            """,
            (fine_id,)
        )

        connection.commit()

        return redirect(url_for("manage_fines"))

    except Exception as e:
        connection.rollback()
        return f"Could not update fine payment. Details: {e}"

    finally:
        cursor.close()
        connection.close()



# RUN APPLICATION
if __name__ == "__main__":
    app.run(debug=True)
