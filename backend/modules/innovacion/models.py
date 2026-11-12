"""
Modelos para el módulo de Innovación - Certificaciones y Eventos.
"""

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, String, Table, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from backend.core.utils import utc_now
from backend.database import Base

# Tag que debe tener un evento para contar como asistencia en las métricas del resumen.
# Match exacto (sensible a mayúsculas/minúsculas).
TAG_ASISTENCIA_RESUMEN = "Track#1"


# === TABLA PIVOT: Asistencia a Eventos ===
evento_asistencia = Table(
    "innovacion_evento_asistencia",
    Base.metadata,
    Column("evento_id", UUID(as_uuid=True), ForeignKey("innovacion_eventos.id"), primary_key=True),
    Column("empleado_id", UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), primary_key=True),
    Column("created_at", DateTime, nullable=False, default=utc_now),
)


class Evento(Base):
    """Evento de innovación al que los empleados pueden asistir."""

    __tablename__ = "innovacion_eventos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)
    nombre = Column(String(200), nullable=False)
    fecha = Column(Date, nullable=False)
    duenio = Column(String(100), nullable=True)
    tags = Column(ARRAY(String), nullable=True, default=[])

    # Soft delete y timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relación M2M con empleados
    asistentes = relationship("Empleado", secondary=evento_asistencia, backref="eventos_innovacion")


# Tipos de certificación estáticos (no necesitan tabla)
TIPOS_CERTIFICACION = {
    "training": {
        "nombre": "Training / Formación",
        "descripcion": "Certificación a través de formación y capacitación",
        "icono": "book-open",
    },
    "iniciativa": {
        "nombre": "Iniciativa / Caso de Uso",
        "descripcion": "Certificación mediante una iniciativa o caso de uso real",
        "icono": "lightbulb",
    },
    "finalista": {
        "nombre": "Finalista del Challenge",
        "descripcion": "Certificación como finalista de un challenge de innovación",
        "icono": "trophy",
    },
}

# Tecnologías predefinidas para autocompletado
TECNOLOGIAS_SUGERIDAS = [
    # Lenguajes de Programación
    "Python",
    "JavaScript",
    "TypeScript",
    "Java",
    "C#",
    "Go",
    "Rust",
    "PHP",
    "Ruby",
    "Swift",
    "Kotlin",
    # Frontend
    "React",
    "Vue.js",
    "Angular",
    "Svelte",
    "Next.js",
    "Nuxt.js",
    "HTML",
    "CSS",
    "Tailwind CSS",
    "Bootstrap",
    # Backend & Frameworks
    "Node.js",
    "Express.js",
    "FastAPI",
    "Django",
    "Flask",
    "Spring Boot",
    "ASP.NET",
    "Laravel",
    "Ruby on Rails",
    # Bases de Datos
    "PostgreSQL",
    "MySQL",
    "MongoDB",
    "Redis",
    "Elasticsearch",
    "SQL Server",
    "Oracle",
    "DynamoDB",
    "Cassandra",
    # Cloud & DevOps
    "AWS",
    "Google Cloud",
    "Azure",
    "Docker",
    "Kubernetes",
    "Terraform",
    "Jenkins",
    "GitLab CI",
    "GitHub Actions",
    # IA & ML
    "TensorFlow",
    "PyTorch",
    "Scikit-learn",
    "Keras",
    "OpenAI",
    "LangChain",
    "Hugging Face",
    "BERT",
    "GPT",
    # Data & Analytics
    "Apache Spark",
    "Apache Kafka",
    "Airflow",
    "dbt",
    "Tableau",
    "Power BI",
    "Pandas",
    "NumPy",
    # Herramientas & Otros
    "Git",
    "n8n",
    "Make",
    "Zapier",
    "Postman",
    "Figma",
    "Jira",
    "Confluence",
    "Slack API",
    "REST API",
    "GraphQL",
]

# Temáticas predefinidas para autocompletado
TEMATICAS_SUGERIDAS = [
    # Áreas de Negocio
    "Data",
    "Education",
    "Finance",
    "Retail",
    "Factory",
    "Healthcare",
    "Logistics",
    "Marketing",
    "Sales",
    "HR",
    # Tecnologías y Dominios
    "AI & Machine Learning",
    "Business Intelligence",
    "Automation",
    "Customer Service",
    "E-commerce",
    "Supply Chain",
    "Quality Assurance",
    "Security",
    "IoT",
    "Blockchain",
    # Procesos
    "Process Optimization",
    "Digital Transformation",
    "Innovation",
    "Analytics",
    "Reporting",
    "Integration",
    "Migration",
]

# Campos requeridos por tipo para calcular progreso.
# fecha_aprobacion NO va acá: es un dato del admin, ajeno al avance del empleado.
CAMPOS_PROGRESO = {
    "finalista": [
        "repo_presentacion",
        "repo_demo",
        "tematica",
        "tecnologias",
        "fecha_presentacion",
    ],
    "training": [
        "cert_noncode_imagen",
        "cert_n8n_imagen",
        "cert_ruta1_imagen",
        "cert_ruta2_imagen",
        "cert_ruta3_imagen",
    ],
    "iniciativa": [
        "repo_presentacion",
        "repo_demo",
        "tematica",
        "tecnologias",
    ],
}


class Certificacion(Base):
    """Certificación de un empleado en un tipo específico."""

    __tablename__ = "innovacion_certificaciones"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    empresa_id = Column(UUID(as_uuid=True), ForeignKey("core_empresas.id"), nullable=False)

    # Relación con empleado
    empleado_id = Column(UUID(as_uuid=True), ForeignKey("nomina_empleados.id"), nullable=False)

    # Tipo de certificación (clave del dict TIPOS_CERTIFICACION)
    tipo_certificacion = Column(String(30), nullable=False)

    # Estado: sin_iniciar, iniciado, en_progreso, en_revision, completada
    estado = Column(String(20), nullable=False, default="sin_iniciar")

    # Campos simples por tipo (se llenan según el wizard)
    titulo = Column(String(200), nullable=True)
    descripcion = Column(Text, nullable=True)

    # === Campos específicos: Finalista del Challenge ===
    # URL del repositorio Git con la presentación del challenge
    repo_presentacion = Column(String(500), nullable=True)
    # URL del repositorio Git con el demo/código funcional
    repo_demo = Column(String(500), nullable=True)
    # Temática o área del challenge (ej: IA, Cloud, DevOps)
    tematica = Column(String(200), nullable=True)
    # Lista de tecnologías usadas en el proyecto (tags)
    tecnologias = Column(ARRAY(String), nullable=True, default=[])
    # Fecha en que se presentó en la Tech-Talk
    fecha_presentacion = Column(Date, nullable=True)
    # Fecha de aprobación (solo editable por admin)
    fecha_aprobacion = Column(Date, nullable=True)

    # === Campos específicos: Training / Formación ===
    # Certificado #1 NoN-Code
    cert_noncode_origen = Column(String(20), nullable=True, default="dicsys")  # 'dicsys' o 'externa'
    cert_noncode_imagen = Column(String(500), nullable=True)
    cert_noncode_fecha = Column(Date, nullable=True)
    cert_noncode_plan = Column(String(500), nullable=True)  # Plan de estudio (solo si externa)
    # Certificado #2 n8n
    cert_n8n_origen = Column(String(20), nullable=True, default="dicsys")  # 'dicsys' o 'externa'
    cert_n8n_imagen = Column(String(500), nullable=True)
    cert_n8n_fecha = Column(Date, nullable=True)
    cert_n8n_plan = Column(String(500), nullable=True)  # Plan de estudio (solo si externa)
    # Certificado #3 Ruta 1 GCP
    cert_ruta1_imagen = Column(String(500), nullable=True)
    cert_ruta1_fecha = Column(Date, nullable=True)
    # Certificado #4 Ruta 2 GCP
    cert_ruta2_imagen = Column(String(500), nullable=True)
    cert_ruta2_fecha = Column(Date, nullable=True)
    # Certificado #5 Ruta 3 GCP
    cert_ruta3_imagen = Column(String(500), nullable=True)
    cert_ruta3_fecha = Column(Date, nullable=True)

    # Progreso: cantidad de campos completados / total campos requeridos
    progreso_completados = Column(String(10), nullable=True, default="0/0")
    porcentaje_avance = Column(String(10), nullable=True, default="0")

    # Fechas de hitos del path
    fecha_registro = Column(DateTime, nullable=True)
    fecha_en_progreso = Column(DateTime, nullable=True)
    fecha_en_presentacion = Column(DateTime, nullable=True)

    # Soft delete y timestamps
    deleted_at = Column(DateTime, nullable=True, default=None)
    created_at = Column(DateTime, nullable=False, default=utc_now)
    updated_at = Column(DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    updated_by = Column(String(255), nullable=True)

    # Relaciones
    empleado_rel = relationship("Empleado", foreign_keys=[empleado_id])

    def calcular_progreso(self):
        """Calcula el % de avance del empleado y los estados automáticos.

        Solo computa avance:
        - sin_iniciar: el tipo no tiene campos de progreso.
        - iniciado: 0 campos cumplidos.
        - en_progreso: 1 o más campos cumplidos (incluido el 100%).

        Los estados que NO dependen del avance se deciden afuera, donde ocurre
        la acción que los provoca:
        - en_revision: lo setea Finalizar en el servicio (avance == 100%).
        - completada: lo setea el admin.

        fecha_aprobacion no participa del cálculo: es un dato del admin.
        """
        campos = list(CAMPOS_PROGRESO.get(self.tipo_certificacion, []))
        if not campos:
            self.progreso_completados = "0/0"
            self.porcentaje_avance = "0"
            self.estado = "sin_iniciar"
            return 0, 0

        # Training: si origen es 'externa', agregar plan de estudio como requisito
        if self.tipo_certificacion == "training":
            if getattr(self, "cert_noncode_origen", None) == "externa":
                campos.append("cert_noncode_plan")
            if getattr(self, "cert_n8n_origen", None) == "externa":
                campos.append("cert_n8n_plan")

        total = len(campos)
        completados = sum(1 for campo in campos if getattr(self, campo, None) not in (None, "", []))

        self.progreso_completados = f"{completados}/{total}"
        self.porcentaje_avance = str(round((completados / total) * 100) if total > 0 else 0)

        # Estado automático: solo refleja el avance del empleado.
        self.estado = "en_progreso" if completados > 0 else "iniciado"

        # Hitos de avance: Registered (existe) e In Progress (algún campo).
        # Submitted (en_revision) y Approved (completada) se estampan donde se
        # deciden esos estados: Finalizar (servicio) y el admin.
        ahora = utc_now()
        if not self.fecha_registro:
            self.fecha_registro = ahora
        if completados > 0 and not self.fecha_en_progreso:
            self.fecha_en_progreso = ahora

        return completados, total
