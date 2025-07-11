import os
from dotenv import load_dotenv
import uuid
from flask import Flask, render_template, redirect, url_for, flash, jsonify, request, abort
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from flask_bcrypt import Bcrypt
from datetime import datetime, date, time, timedelta
import cloudinary
import cloudinary.uploader
import cloudinary.api
from sqlalchemy import func, extract
from collections import defaultdict
import mercadopago
from functools import wraps

load_dotenv()

# --- CONFIGURAÇÃO DA APLICAÇÃO ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'uma-chave-secreta-muito-segura-e-diferente-para-testes'
basedir = os.path.abspath(os.path.dirname(__file__))
render_db_url = os.environ.get('DATABASE_URL')
if render_db_url and render_db_url.startswith("postgres://"):
    render_db_url = render_db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = render_db_url or 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- INICIALIZAÇÃO DAS EXTENSÕES ---
from models import db, User, Patient, Appointment, ElectronicRecord, Assessment, UploadedFile, Clinic, Exercise
db.init_app(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça o login para aceder a esta página.'
login_manager.login_message_category = 'info'

# --- CONFIGURAÇÃO DOS SDKs ---
mp_sdk = mercadopago.SDK(os.environ.get("MERCADO_PAGO_ACCESS_TOKEN"))
cloudinary.config(cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'), api_key=os.environ.get('CLOUDINARY_API_KEY'), api_secret=os.environ.get('CLOUDINARY_API_SECRET'), secure=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_global_variables():
    return {'current_year': datetime.utcnow().year, 'today': date.today()}

@app.template_filter('datetimeformat')
def format_datetime_filter(s, format='%d/%m/%Y'):
    if isinstance(s, str):
        try: s = datetime.strptime(s, '%Y-%m-%d').date()
        except ValueError: return s
    if hasattr(s, 'strftime'): return s.strftime(format)
    return s

# --- DECORADORES DE ACESSO (DESABILITADOS PARA TESTE) ---
def access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # A verificação de acesso está desabilitada para testes.
        # Lembre-se de reativar em produção, removendo os comentários abaixo.
        # if not current_user.is_authenticated or not current_user.clinic.access_expires_on or current_user.clinic.access_expires_on < datetime.utcnow():
        #     flash('O seu acesso expirou ou não está ativo. Por favor, adquira um passe para continuar.', 'warning')
        #     return redirect(url_for('pricing'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Para testes, esta verificação também pode ser comentada se necessário.
        # if not current_user.is_authenticated or current_user.role != 'admin':
        #     flash('Você não tem permissão para aceder a esta página.', 'danger')
        #     return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROTAS DE PAGAMENTO E SUBSCRIÇÃO ---
@app.route('/pricing')
#@login_required
def pricing():
    return render_template('pricing_checkout_pro.html', title="Passes de Acesso")

@app.route('/create-payment/<plan_type>')
#@login_required
def create_payment(plan_type):
    if plan_type == 'anual':
        price = 599.00
        title = "Acesso Anual FisioManager"
    else: # Mensal como padrão
        price = 59.90
        title = "Acesso Mensal FisioManager"

    # Para testes sem login, usamos um email e ID de clínica fixos
    payer_email = "cliente_teste@email.com"
    clinic_id = 1 # Assumindo que a primeira clínica é a de teste
    if current_user.is_authenticated:
        payer_email = current_user.email
        clinic_id = current_user.clinic_id

    external_reference = f"clinic_{clinic_id}_plan_{plan_type}_{uuid.uuid4()}"

    preference_data = {
        "items": [{"title": title, "quantity": 1, "unit_price": price}],
        "payer": {"email": payer_email},
        "back_urls": {
            "success": url_for('dashboard', _external=True),
            "failure": url_for('pricing', _external=True),
            "pending": url_for('pricing', _external=True)
        },
        "auto_return": "approved",
        "external_reference": external_reference,
        "notification_url": url_for('mercadopago_ipn', _external=True)
    }

    try:
        preference_result = mp_sdk.preference().create(preference_data)
        if preference_result["status"] == 201:
            return redirect(preference_result["response"]["init_point"])
        else:
            flash("Erro ao criar preferência de pagamento.", 'danger')
            return redirect(url_for('pricing'))
    except Exception as e:
        app.logger.error(f"Erro na API do Mercado Pago: {e}")
        flash("Ocorreu um erro ao comunicar com o sistema de pagamentos.", 'danger')
        return redirect(url_for('pricing'))

@app.route('/mercadopago-ipn', methods=['POST'])
def mercadopago_ipn():
    data = request.get_json()
    if data and data.get("type") == "payment":
        payment_id = data.get("data", {}).get("id")
        if payment_id:
            try:
                payment_info = mp_sdk.payment().get(payment_id)
                if payment_info["status"] == 200:
                    payment = payment_info["response"]
                    if payment.get("status") == "approved":
                        external_ref = payment.get("external_reference")
                        if external_ref and external_ref.startswith("clinic_"):
                            parts = external_ref.split('_')
                            clinic_id = int(parts[1])
                            plan_type = parts[3]
                            
                            clinic = Clinic.query.get(clinic_id)
                            if clinic:
                                duration = 365 if plan_type == 'anual' else 30
                                current_expiry = clinic.access_expires_on or datetime.utcnow()
                                if current_expiry < datetime.utcnow():
                                    current_expiry = datetime.utcnow()
                                
                                clinic.access_expires_on = current_expiry + timedelta(days=duration)
                                db.session.commit()
            except Exception as e:
                app.logger.error(f"Erro ao processar IPN do MP: {e}")
                return "Erro", 500
    return "OK", 200

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    from forms import RegistrationForm
    form = RegistrationForm()
    if form.validate_on_submit():
        new_clinic = Clinic(name=f"Clínica de {form.name.data}")
        db.session.add(new_clinic)
        db.session.commit()
        user = User(name=form.name.data, email=form.email.data, clinic_id=new_clinic.id, role='admin')
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Sua conta de administrador foi criada com sucesso!', 'success')
        login_user(user)
        return redirect(url_for('dashboard'))
    return render_template('register.html', title='Registrar', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    from forms import LoginForm
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login sem sucesso. Verifique o seu email e senha.', 'danger')
    return render_template('login.html', title='Login', form=form)

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- ROTAS PRINCIPAIS E DE GESTÃO ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
#@login_required
#@access_required
def dashboard():
    hoje = date.today()
    clinic_id = 1 # ID fixo para testes
    if current_user.is_authenticated:
        clinic_id = current_user.clinic_id
    
    all_patients = Patient.query.filter_by(clinic_id=clinic_id).all()
    total_patients = len(all_patients)
    
    gender_data = defaultdict(int)
    for patient in all_patients:
        gender_data[patient.gender or "Não Esp."] += 1

    specialty_data = db.session.query(Patient.specialty, func.count(Patient.id)).filter(Patient.clinic_id == clinic_id).group_by(Patient.specialty).all()
    specialty_chart_data = {label if label else "N/A": count for label, count in specialty_data}

    age_groups = {"0-18": 0, "19-30": 0, "31-50": 0, "51+": 0}
    for patient in all_patients:
        age = patient.age
        if age <= 18: age_groups["0-18"] += 1
        elif age <= 30: age_groups["19-30"] += 1
        elif age <= 50: age_groups["31-50"] += 1
        else: age_groups["51+"] += 1
    start_of_month = hoje.replace(day=1)
    appointments_per_patient = db.session.query(Patient, func.count(Appointment.id)).outerjoin(Appointment, (Patient.id == Appointment.patient_id) & (Appointment.status == 'Concluído') & (extract('month', Appointment.start_time) == hoje.month) & (extract('year', Appointment.start_time) == hoje.year)).filter(Patient.clinic_id == clinic_id).group_by(Patient.id).order_by(func.count(Appointment.id).desc()).all()
    
    return render_template(
        'dashboard.html',
        title="Dashboard",
        gender_data=dict(gender_data),
        total_patients=total_patients,
        specialty_data=specialty_chart_data,
        age_data=age_groups,
        patient_appointment_counts=appointments_per_patient
    )

@app.route('/agenda')
#@login_required
#@access_required
def agenda():
    return render_template('agenda_grid.html')

@app.route('/patients')
#@login_required
#@access_required
def list_patients():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('q', '')
    clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
    patients_query = Patient.query.filter_by(clinic_id=clinic_id_to_use)
    if search_query:
        patients_query = patients_query.filter(Patient.full_name.ilike(f'%{search_query}%'))
    patients_pagination = patients_query.order_by(Patient.full_name).paginate(page=page, per_page=10)
    patients_enriched = []
    for patient in patients_pagination.items:
        appointment_count = patient.appointments.count()
        latest_record = patient.records.order_by(ElectronicRecord.record_date.desc()).first()
        latest_diagnosis = latest_record.medical_diagnosis if (latest_record and latest_record.medical_diagnosis) else "N/A"
        patients_enriched.append({'data': patient, 'appointment_count': appointment_count, 'latest_diagnosis': latest_diagnosis})
    return render_template('list_patients.html', patients_pagination=patients_pagination, patients_enriched=patients_enriched, search_query=search_query, title="Painel de Pacientes")

@app.route('/professionals')
#@login_required
#@admin_required
def list_professionals():
    clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
    professionals = User.query.filter_by(clinic_id=clinic_id_to_use).all()
    return render_template('list_professionals.html', professionals=professionals, title="Gerir Profissionais")

@app.route('/professional/add', methods=['GET', 'POST'])
#@login_required
#@admin_required
def add_professional():
    from forms import ProfessionalForm
    form = ProfessionalForm()
    if form.validate_on_submit():
        clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
        new_professional = User(name=form.name.data, email=form.email.data, role=form.role.data, date_of_birth=form.date_of_birth.data, cpf=form.cpf.data, address=form.address.data, phone=form.phone.data, crefito=form.crefito.data, clinic_id=clinic_id_to_use)
        if form.password.data:
            new_professional.set_password(form.password.data)
        else:
            new_professional.set_password('fisiomanager123')
        db.session.add(new_professional)
        db.session.commit()
        flash('Novo profissional adicionado com sucesso!', 'success')
        return redirect(url_for('list_professionals'))
    return render_template('add_edit_professional.html', form=form, title="Adicionar Profissional")

@app.route('/professional/<int:professional_id>/edit', methods=['GET', 'POST'])
#@login_required
#@admin_required
def edit_professional(professional_id):
    professional = User.query.get_or_404(professional_id)
    # if professional.clinic_id != current_user.clinic_id: abort(403)
    from forms import ProfessionalForm
    form = ProfessionalForm(obj=professional)
    if form.validate_on_submit():
        professional.name = form.name.data
        professional.email = form.email.data
        professional.role = form.role.data
        professional.date_of_birth = form.date_of_birth.data
        professional.cpf = form.cpf.data
        professional.address = form.address.data
        professional.phone = form.phone.data
        professional.crefito = form.crefito.data
        if form.password.data:
            professional.set_password(form.password.data)
        db.session.commit()
        flash('Dados do profissional atualizados com sucesso!', 'success')
        return redirect(url_for('list_professionals'))
    return render_template('add_edit_professional.html', form=form, title="Editar Profissional")

@app.route('/professional/<int:professional_id>/delete', methods=['POST'])
#@login_required
#@admin_required
def delete_professional(professional_id):
    professional = User.query.get_or_404(professional_id)
    # if professional.clinic_id != current_user.clinic_id or professional.id == current_user.id:
    #     flash('Não é possível apagar a sua própria conta de administrador.', 'danger')
    #     return redirect(url_for('list_professionals'))
    db.session.delete(professional)
    db.session.commit()
    flash('Profissional apagado com sucesso.', 'success')
    return redirect(url_for('list_professionals'))

@app.route('/exercises')
#@login_required
#@access_required
def list_exercises():
    clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
    exercises = Exercise.query.filter_by(clinic_id=clinic_id_to_use).order_by(Exercise.name).all()
    return render_template('list_exercises.html', exercises=exercises, title="Biblioteca de Exercícios")

@app.route('/exercise/add', methods=['GET', 'POST'])
#@login_required
#@access_required
def add_exercise():
    from forms import ExerciseForm
    form = ExerciseForm()
    if form.validate_on_submit():
        clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
        new_exercise = Exercise(name=form.name.data, description=form.description.data, instructions=form.instructions.data, video_url=form.video_url.data, clinic_id=clinic_id_to_use)
        db.session.add(new_exercise)
        db.session.commit()
        flash('Exercício adicionado com sucesso!', 'success')
        return redirect(url_for('list_exercises'))
    return render_template('add_edit_exercise.html', form=form, title="Adicionar Exercício")

@app.route('/exercise/<int:exercise_id>/edit', methods=['GET', 'POST'])
#@login_required
#@access_required
def edit_exercise(exercise_id):
    exercise = Exercise.query.get_or_404(exercise_id)
    # if exercise.clinic_id != current_user.clinic_id: abort(403)
    from forms import ExerciseForm
    form = ExerciseForm(obj=exercise)
    if form.validate_on_submit():
        exercise.name = form.name.data
        exercise.description = form.description.data
        exercise.instructions = form.instructions.data
        exercise.video_url = form.video_url.data
        db.session.commit()
        flash('Exercício atualizado com sucesso!', 'success')
        return redirect(url_for('list_exercises'))
    return render_template('add_edit_exercise.html', form=form, title="Editar Exercício")

@app.route('/exercise/<int:exercise_id>/delete', methods=['POST'])
#@login_required
#@access_required
def delete_exercise(exercise_id):
    exercise = Exercise.query.get_or_404(exercise_id)
    # if exercise.clinic_id != current_user.clinic_id: abort(403)
    db.session.delete(exercise)
    db.session.commit()
    flash('Exercício apagado com sucesso.', 'success')
    return redirect(url_for('list_exercises'))

@app.route('/patient/add', methods=['GET', 'POST'])
#@login_required
#@access_required
def add_patient():
    from forms import PatientForm
    form = PatientForm()
    if form.validate_on_submit():
        clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
        user_to_use = current_user if current_user.is_authenticated else User.query.get(1)
        new_patient = Patient(full_name=form.full_name.data, date_of_birth=form.date_of_birth.data, gender=form.gender.data, phone=form.phone.data, specialty=form.specialty.data, professional=user_to_use, clinic_id=clinic_id_to_use)
        db.session.add(new_patient)
        db.session.commit()
        flash('Paciente cadastrado com sucesso!', 'success')
        return redirect(url_for('list_patients'))
    return render_template('add_edit_patient.html', form=form, title="Adicionar Paciente")

@app.route('/patient/<int:patient_id>/edit', methods=['GET', 'POST'])
#@login_required
#@access_required
def edit_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    # if patient.clinic_id != current_user.clinic_id: abort(403)
    from forms import PatientForm
    form = PatientForm(obj=patient)
    if form.validate_on_submit():
        patient.full_name = form.full_name.data
        patient.date_of_birth = form.date_of_birth.data
        patient.gender = form.gender.data
        patient.phone = form.phone.data
        patient.specialty = form.specialty.data
        db.session.commit()
        flash('Dados do paciente atualizados com sucesso!', 'success')
        return redirect(url_for('list_patients'))
    return render_template('add_edit_patient.html', form=form, title="Editar Paciente")

@app.route('/patient/<int:patient_id>/delete', methods=['POST'])
#@login_required
#@access_required
def delete_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    # if patient.clinic_id != current_user.clinic_id: abort(403)
    db.session.delete(patient)
    db.session.commit()
    flash(f'O paciente {patient.full_name} e todos os seus registos foram apagados com sucesso.', 'success')
    return redirect(url_for('list_patients'))

@app.route('/patient/<int:patient_id>')
#@login_required
#@access_required
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    # if patient.clinic_id != current_user.clinic_id: abort(403)
    records = patient.records.order_by(ElectronicRecord.record_date.desc()).all()
    assessments = patient.assessments.order_by(Assessment.created_at.desc()).all()
    return render_template('patient_detail.html', patient=patient, records=records, assessments=assessments)

@app.route('/patient/<int:patient_id>/add_record', methods=['GET', 'POST'])
#@login_required
#@access_required
def add_record(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    # if patient.clinic_id != current_user.clinic_id: abort(403)
    from forms import ElectronicRecordForm
    form = ElectronicRecordForm()
    if form.validate_on_submit():
        record = ElectronicRecord(record_date=datetime.utcnow(), medical_diagnosis=form.medical_diagnosis.data, subjective_notes=form.subjective_notes.data, objective_notes=form.objective_notes.data, assessment=form.assessment.data, plan=form.plan.data, patient_id=patient.id)
        db.session.add(record)
        db.session.commit()
        flash('Registro adicionado ao prontuário com sucesso!', 'success')
        return redirect(url_for('patient_detail', patient_id=patient.id))
    return render_template('add_record.html', form=form, patient=patient, title="Adicionar ao Prontuário")

@app.route('/patient/<int:patient_id>/add_assessment', methods=['GET', 'POST'])
#@login_required
#@access_required
def add_assessment(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    # if patient.clinic_id != current_user.clinic_id: abort(403)
    from forms import AssessmentForm
    form = AssessmentForm()
    if form.validate_on_submit():
        assessment = Assessment(patient_id=patient.id, main_complaint=form.main_complaint.data, history_of_present_illness=form.history_of_present_illness.data, past_medical_history=form.past_medical_history.data, medications=form.medications.data, social_history=form.social_history.data, inspection_notes=form.inspection_notes.data, palpation_notes=form.palpation_notes.data, mobility_assessment=form.mobility_assessment.data, strength_assessment=form.strength_assessment.data, neuro_assessment=form.neuro_assessment.data, functional_assessment=form.functional_assessment.data, diagnosis=form.diagnosis.data, goals=form.goals.data, treatment_plan=form.treatment_plan.data)
        db.session.add(assessment)
        db.session.commit()
        files = request.files.getlist(form.files.name)
        for file in files:
            if file:
                upload_result = cloudinary.uploader.upload(file)
                new_file = UploadedFile(public_id=upload_result['public_id'], secure_url=upload_result['secure_url'], resource_type=upload_result['resource_type'], assessment_id=assessment.id)
                db.session.add(new_file)
        db.session.commit()
        flash('Nova avaliação salva com sucesso!', 'success')
        return redirect(url_for('patient_detail', patient_id=patient.id))
    return render_template('add_edit_assessment.html', title='Nova Avaliação', form=form, patient=patient)

@app.route('/assessment/<int:assessment_id>')
#@login_required
#@access_required
def view_assessment(assessment_id):
    assessment = Assessment.query.get_or_404(assessment_id)
    # if assessment.patient.clinic_id != current_user.clinic_id: abort(403)
    return render_template('view_assessment.html', title='Detalhes da Avaliação', assessment=assessment)

@app.route('/reports')
#@login_required
#@access_required
def reports():
    hoje = date.today()
    start_date_str = request.args.get('start_date')
    end_date_str = request.args.get('end_date')
    if start_date_str and end_date_str:
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    else:
        start_date = hoje.replace(day=1)
        next_month = start_date.replace(day=28) + timedelta(days=4)
        end_date = next_month - timedelta(days=next_month.day)
    start_datetime = datetime.combine(start_date, time.min)
    end_datetime = datetime.combine(end_date, time.max)
    
    clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
    
    financial_appointments = db.session.query(Appointment).join(User).filter(User.clinic_id == clinic_id_to_use, Appointment.start_time.between(start_datetime, end_datetime)).order_by(Appointment.start_time.desc()).all()
    total_cobrado_periodo = sum(appt.session_price for appt in financial_appointments if appt.session_price)
    total_recebido_periodo = sum(appt.amount_paid for appt in financial_appointments if appt.amount_paid)
    start_of_current_month = hoje.replace(day=1)
    appointments_this_month = db.session.query(Appointment).join(User).filter(User.clinic_id == clinic_id_to_use, Appointment.start_time >= start_of_current_month).all()
    status_counts = {'Concluído': 0, 'Agendado': 0, 'Cancelado': 0}
    for appt in appointments_this_month:
        if appt.status in status_counts: status_counts[appt.status] += 1
    return render_template('reports.html', financial_appointments=financial_appointments, total_cobrado=total_cobrado_periodo, total_recebido=total_recebido_periodo, start_date=start_date.strftime('%Y-%m-%d'), end_date=end_date.strftime('%Y-%m-%d'), status_counts=status_counts)


# --- APIS ---
@app.route('/api/appointments')
#@login_required
#@access_required
def api_appointments():
    clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
    appointments = db.session.query(Appointment).join(User).filter(User.clinic_id == clinic_id_to_use).all()
    status_colors = {'Concluído': '#198754', 'Agendado': '#0dcaf0', 'Cancelado': '#6c757d'}
    eventos = []
    for appt in appointments:
        eventos.append({'id': appt.id, 'title': appt.patient.full_name, 'start': appt.start_time.isoformat(), 'color': status_colors.get(appt.status, '#6c757d'), 'borderColor': status_colors.get(appt.status, '#6c757d'), 'extendedProps': {'location': appt.location, 'status': appt.status, 'notes': appt.notes, 'session_price': appt.session_price, 'amount_paid': appt.amount_paid, 'payment_notes': appt.payment_notes, 'patient_id': appt.patient_id, 'recurrence_id': appt.recurrence_id}})
    return jsonify(eventos)

@app.route('/api/patients')
#@login_required
def api_patients():
    clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
    patients = Patient.query.filter_by(clinic_id=clinic_id_to_use).order_by(Patient.full_name).all()
    return jsonify([{'id': p.id, 'name': p.full_name} for p in patients])

@app.route('/api/appointment/<int:appointment_id>/<action>', methods=['POST'])
#@login_required
def handle_appointment_action(appointment_id, action):
    clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
    appointment = db.session.query(Appointment).join(User).filter(Appointment.id == appointment_id, User.clinic_id == clinic_id_to_use).first_or_404()
    if action == 'complete': appointment.status = 'Concluído'; message = 'Agendamento marcado como concluído.'
    elif action == 'cancel': appointment.status = 'Cancelado'; message = 'Agendamento cancelado com sucesso.'
    elif action == 'delete': db.session.delete(appointment); message = 'Agendamento apagado permanentemente.'
    else: return jsonify({'status': 'error', 'message': 'Ação inválida.'}), 400
    db.session.commit()
    return jsonify({'status': 'success', 'message': message})

@app.route('/api/appointment/<int:appointment_id>/update', methods=['POST'])
#@login_required
def update_appointment(appointment_id):
    clinic_id_to_use = current_user.clinic_id if current_user.is_authenticated else 1
    appointment = db.session.query(Appointment).join(User).filter(Appointment.id == appointment_id, User.clinic_id == clinic_id_to_use).first_or_404()
    data = request.get_json()
    try:
        if 'start_time' in data and data['start_time']: appointment.start_time = datetime.fromisoformat(data['start_time'].replace('Z', '+00:00'))
        if 'location' in data: appointment.location = data['location']
        if 'notes' in data: appointment.notes = data['notes']
        if 'session_price' in data: appointment.session_price = float(data.get('session_price', 0.0) or 0.0)
        if 'amount_paid' in data: appointment.amount_paid = float(data.get('amount_paid', 0.0) or 0.0)
        if 'payment_notes' in data: appointment.payment_notes = data.get('payment_notes', '')
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Agendamento atualizado com sucesso.'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'status': 'error', 'message': f'Ocorreu um erro interno: {e}'}), 500

# --- COMANDO PARA INICIALIZAR O BANCO DE DADOS ---
@app.cli.command("init-db")
def init_db_command():
    db.create_all()
    print("Banco de dados inicializado e tabelas criadas.")

if __name__ == '__main__':
    app.run(debug=True)































