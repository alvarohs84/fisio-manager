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

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'uma-chave-secreta-muito-segura'
basedir = os.path.abspath(os.path.dirname(__file__))
render_db_url = os.environ.get('DATABASE_URL')
if render_db_url and render_db_url.startswith("postgres://"):
    render_db_url = render_db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = render_db_url or 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

from models import db, User, Patient, Appointment, ElectronicRecord, Assessment, UploadedFile, Clinic
db.init_app(app)
migrate = Migrate(app, db)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça o login para aceder a esta página.'
login_manager.login_message_category = 'info'

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

def access_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Você não tem permissão para aceder a esta página.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROTAS DE GESTÃO DE PROFISSIONAIS ---
@app.route('/professionals')
@login_required
@admin_required
def list_professionals():
    professionals = User.query.filter_by(clinic_id=current_user.clinic_id).all()
    return render_template('list_professionals.html', professionals=professionals, title="Gerir Profissionais")

@app.route('/professional/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_professional():
    from forms import ProfessionalForm
    form = ProfessionalForm()
    if form.validate_on_submit():
        new_professional = User(
            name=form.name.data,
            email=form.email.data,
            role=form.role.data,
            date_of_birth=form.date_of_birth.data,
            cpf=form.cpf.data,
            address=form.address.data,
            phone=form.phone.data,
            crefito=form.crefito.data,
            clinic_id=current_user.clinic_id
        )
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
@login_required
@admin_required
def edit_professional(professional_id):
    professional = User.query.get_or_404(professional_id)
    if professional.clinic_id != current_user.clinic_id:
        abort(403)
    
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
@login_required
@admin_required
def delete_professional(professional_id):
    professional = User.query.get_or_404(professional_id)
    if professional.clinic_id != current_user.clinic_id or professional.id == current_user.id:
        flash('Não é possível apagar a sua própria conta de administrador.', 'danger')
        return redirect(url_for('list_professionals'))
    
    db.session.delete(professional)
    db.session.commit()
    flash('Profissional apagado com sucesso.', 'success')
    return redirect(url_for('list_professionals'))

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
    return render_template('add_assessment.html', title='Nova Avaliação', form=form, patient=patient)

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
















