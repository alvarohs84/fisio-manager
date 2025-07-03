# app.py (COMPLETO E ATUALIZADO COM CHECKOUT PRO)

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
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or 'uma-chave-secreta-muito-segura'
basedir = os.path.abspath(os.path.dirname(__file__))
render_db_url = os.environ.get('DATABASE_URL')
if render_db_url and render_db_url.startswith("postgres://"):
    render_db_url = render_db_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = render_db_url or 'sqlite:///' + os.path.join(basedir, 'app.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- IDS DOS PLANOS DO MERCADO PAGO ---
app.config['MERCADO_PAGO_PLANO_MENSAL_ID'] = os.environ.get('MP_PLANO_MENSAL_ID')
app.config['MERCADO_PAGO_PLANO_ANUAL_ID'] = os.environ.get('MP_PLANO_ANUAL_ID')


# --- INICIALIZAÇÃO DAS EXTENSÕES ---
from models import db, User, Patient, Appointment, ElectronicRecord, Assessment, UploadedFile, Clinic
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

# --- DECORADOR PARA VERIFICAR SUBSCRIÇÃO ATIVA ---
def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.clinic.subscription_status != 'active':
            flash('A sua subscrição não está ativa. Por favor, escolha um plano para continuar.', 'warning')
            return redirect(url_for('pricing'))
        return f(*args, **kwargs)
    return decorated_function

# --- ROTAS DE PAGAMENTO E SUBSCRIÇÃO ---
@app.route('/pricing')
@login_required
def pricing():
    return render_template('pricing_mercadopago.html', title="Planos e Preços")

@app.route('/create-subscription/<plan_type>')
@login_required
def create_subscription(plan_type):
    if plan_type == 'mensal':
        plan_id = app.config['MERCADO_PAGO_PLANO_MENSAL_ID']
    elif plan_type == 'anual':
        plan_id = app.config['MERCADO_PAGO_PLANO_ANUAL_ID']
    else:
        abort(404)
        
    if not plan_id:
        flash("Os IDs dos planos de subscrição não estão configurados no servidor.", 'danger')
        return redirect(url_for('pricing'))

    subscription_data = {
        "preapproval_plan_id": plan_id,
        "reason": f"Assinatura FisioManager - Plano {plan_type.capitalize()}",
        "payer_email": current_user.email,
        "back_url": url_for('dashboard', _external=True)
    }
    
    try:
        result = mp_sdk.preapproval().create(subscription_data)
        
        if result["status"] == 201:
            current_user.clinic.mp_subscription_id = result["response"]["id"]
            db.session.commit()
            payment_link = result["response"]["init_point"]
            return redirect(payment_link)
        else:
            flash(f"Erro inesperado do Mercado Pago: {result.get('response', {}).get('message', 'Sem detalhes')}", 'danger')
            return redirect(url_for('pricing'))

    except mercadopago.exceptions.MPException as e:
        app.logger.error(f"Erro na API do Mercado Pago: {e.message}")
        flash(f"Erro ao criar subscrição: {e.message}", 'danger')
        return redirect(url_for('pricing'))
    except Exception as e:
        app.logger.error(f"Erro inesperado: {e}")
        flash("Ocorreu um erro de comunicação. Tente novamente.", 'danger')
        return redirect(url_for('pricing'))


@app.route('/mercadopago-webhook', methods=['POST'])
def mercadopago_webhook():
    data = request.get_json()
    if data and data.get("type") == "preapproval":
        subscription_id = data.get("data", {}).get("id")
        if subscription_id:
            try:
                subscription_details = mp_sdk.preapproval().get(subscription_id)
                if subscription_details["status"] == 200:
                    response = subscription_details["response"]
                    clinic = Clinic.query.filter_by(mp_subscription_id=subscription_id).first()
                    if clinic:
                        new_status = response.get("status")
                        if new_status == "authorized":
                            clinic.subscription_status = "active"
                        else:
                            clinic.subscription_status = "inactive"
                        db.session.commit()
            except Exception as e:
                app.logger.error(f"Erro ao processar webhook do MP: {e}")
                return "Erro no processamento", 500
    return "OK", 200

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    from forms import RegistrationForm
    form = RegistrationForm()
    if form.validate_on_submit():
        new_clinic = Clinic(name=f"Clínica de {form.name.data}", subscription_status='inactive')
        db.session.add(new_clinic)
        db.session.commit()
        user = User(name=form.name.data, email=form.email.data, clinic_id=new_clinic.id)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Sua conta e sua clínica foram criadas com sucesso! Escolha um plano para começar.', 'success')
        login_user(user)
        return redirect(url_for('pricing'))
    return render_template('register.html', title='Registrar', form=form)

# ... (O resto do seu app.py continua aqui, sem alterações)
```

---

### **Passo 2: O Frontend (`templates/pricing_mercadopago.html`)**

Vamos criar um ficheiro de preços específico para este fluxo de redirecionamento. Ele terá botões simples que apontam para a nossa rota `create_subscription`.

**Ação:** Crie um novo ficheiro chamado `pricing_mercadopago.html` na sua pasta `templates` (ou substitua o existente).

```html
{% extends "base.html" %}

{% block content %}
<div class="container py-3">
  <header>
    <div class="pricing-header p-3 pb-md-4 mx-auto text-center">
      <h1 class="display-4 fw-normal">Planos e Preços</h1>
      <p class="fs-5 text-muted">Escolha o plano que melhor se adapta à sua clínica. Pagamento seguro e simplificado com o Mercado Pago, incluindo Pix, Boleto e Cartão.</p>
    </div>
  </header>

  <main>
    <div class="row row-cols-1 row-cols-md-2 mb-3 text-center justify-content-center">
      
      <!-- Card do Plano Mensal -->
      <div class="col">
        <div class="card mb-4 rounded-3 shadow-sm">
          <div class="card-header py-3">
            <h4 class="my-0 fw-normal">Plano Mensal</h4>
          </div>
          <div class="card-body">
            <h1 class="card-title pricing-card-title">R$59<small class="text-muted fw-light">,90/mês</small></h1>
            <ul class="list-unstyled mt-3 mb-4">
              <li>Gestão de Pacientes Ilimitada</li>
              <li>Agenda de Atendimentos</li>
              <li>Prontuário Eletrônico</li>
              <li>Relatórios e Análises</li>
            </ul>
            <!-- Este link aponta para a nossa rota no app.py -->
            <a href="{{ url_for('create_subscription', plan_type='mensal') }}" class="w-100 btn btn-lg btn-outline-primary">Assinar Plano Mensal</a>
          </div>
        </div>
      </div>

      <!-- Card do Plano Anual -->
      <div class="col">
        <div class="card mb-4 rounded-3 shadow-sm border-primary">
          <div class="card-header py-3 text-white bg-primary border-primary">
            <h4 class="my-0 fw-normal">Plano Anual</h4>
          </div>
          <div class="card-body">
            <h1 class="card-title pricing-card-title">R$599<small class="text-muted fw-light">,00/ano</small></h1>
            <ul class="list-unstyled mt-3 mb-4">
              <li><strong>Desconto de 2 meses!</strong></li>
              <li>Todas as funcionalidades incluídas</li>
              <li>Suporte prioritário</li>
            </ul>
            <!-- Este link aponta para a nossa rota no app.py -->
            <a href="{{ url_for('create_subscription', plan_type='anual') }}" class="w-100 btn btn-lg btn-primary">Assinar Plano Anual</a>
          </div>
        </div>
      </div>
    </div>
  </main>
</div>
{% endblock %}
```

---




