--
-- PostgreSQL database dump
--

\restrict on0jbQJPv6XI2q9Wd1mV4vpeqblX7BHvCwjOZwSLdtFgW4DcJ1T7zFPdRHps5Jq

-- Dumped from database version 16.13
-- Dumped by pg_dump version 16.13

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: pgcrypto; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA public;


--
-- Name: EXTENSION pgcrypto; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION pgcrypto IS 'cryptographic functions';


--
-- Name: unaccent; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA public;


--
-- Name: EXTENSION unaccent; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION unaccent IS 'text search dictionary that removes accents';


--
-- Name: uuid-ossp; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA public;


--
-- Name: EXTENSION "uuid-ossp"; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION "uuid-ossp" IS 'generate universally unique identifiers (UUIDs)';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: admin_categorias_cliente; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_categorias_cliente (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    descripcion character varying(255),
    activo boolean NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: admin_cliente_categoria; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_cliente_categoria (
    cliente_id uuid NOT NULL,
    categoria_id uuid NOT NULL,
    created_at timestamp without time zone
);


--
-- Name: admin_cliente_domicilios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_cliente_domicilios (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    cliente_id uuid NOT NULL,
    calle character varying(200) NOT NULL,
    numero character varying(20),
    piso character varying(20),
    departamento character varying(20),
    localidad character varying(100) NOT NULL,
    provincia character varying(100) NOT NULL,
    pais character varying(100) NOT NULL,
    codigo_postal character varying(10),
    vigente boolean NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: admin_clientes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.admin_clientes (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    tipo character varying(20) NOT NULL,
    cuit character varying(13) NOT NULL,
    razon_social character varying(200) NOT NULL,
    nombre_fantasia character varying(200),
    responsabilidad_afip character varying(50) NOT NULL,
    sitio_web character varying(255),
    logo character varying(500),
    activo boolean NOT NULL,
    observaciones text,
    nro_ingresos_brutos character varying(50),
    fecha_inicio_actividades date,
    nro_inscripcion_municipal character varying(50),
    regimen_retencion character varying(100),
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: administracion_recibos_export; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.administracion_recibos_export (
    id uuid NOT NULL,
    colaborador character varying(200),
    cliente character varying(100),
    apellido character varying(100),
    nombre character varying(100),
    dni bigint,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: core_auditoria_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_auditoria_log (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    fecha_hora timestamp without time zone NOT NULL,
    modulo character varying(100) NOT NULL,
    ruta character varying(500) NOT NULL,
    metodo character varying(10) NOT NULL,
    email_usuario character varying(255) NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: core_empresa_domicilios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_empresa_domicilios (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    calle character varying(200) NOT NULL,
    numero character varying(20),
    piso character varying(20),
    departamento character varying(20),
    localidad character varying(100) NOT NULL,
    provincia character varying(100) NOT NULL,
    pais character varying(100) NOT NULL,
    codigo_postal character varying(10),
    vigente boolean NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: core_empresas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_empresas (
    id uuid NOT NULL,
    cuit character varying(13) NOT NULL,
    razon_social character varying(200) NOT NULL,
    nombre_fantasia character varying(200),
    responsabilidad_afip character varying(50) NOT NULL,
    logo character varying(500),
    sitio_web character varying(255),
    telefono character varying(30),
    email_contacto character varying(255),
    observaciones text,
    dominios_email text,
    activo boolean NOT NULL,
    nro_ingresos_brutos character varying(50),
    fecha_inicio_actividades date,
    nro_inscripcion_municipal character varying(50),
    regimen_retencion character varying(100),
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: core_envios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_envios (
    id uuid NOT NULL,
    origen character varying(100) NOT NULL,
    canal character varying(20) NOT NULL,
    destino character varying(255) NOT NULL,
    asunto character varying(300),
    contenido jsonb NOT NULL,
    clave character varying(300),
    referencia character varying(120),
    estado character varying(20) NOT NULL,
    intentos integer NOT NULL,
    proximo_intento_at timestamp without time zone NOT NULL,
    error text,
    enviado_at timestamp without time zone,
    creada_at timestamp without time zone NOT NULL,
    alerta_enviada boolean NOT NULL,
    CONSTRAINT ck_core_envios_canal CHECK (((canal)::text = ANY ((ARRAY['email'::character varying, 'webex_personal'::character varying, 'webex_room'::character varying])::text[]))),
    CONSTRAINT ck_core_envios_estado CHECK (((estado)::text = ANY ((ARRAY['pendiente'::character varying, 'enviado'::character varying, 'error'::character varying])::text[])))
);


--
-- Name: core_grupo_departamento; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_grupo_departamento (
    grupo_id uuid NOT NULL,
    departamento_id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    created_at timestamp without time zone
);


--
-- Name: core_grupo_menu; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_grupo_menu (
    grupo_id uuid NOT NULL,
    menu_id uuid NOT NULL,
    puede_ver boolean,
    puede_acceder boolean,
    created_at timestamp without time zone
);


--
-- Name: core_grupos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_grupos (
    id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    descripcion character varying(255),
    activo boolean,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone
);


--
-- Name: core_llm_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_llm_requests (
    id uuid NOT NULL,
    modulo character varying(50) NOT NULL,
    model_name character varying(100) NOT NULL,
    periodo character varying(7) NOT NULL,
    tokens_input integer NOT NULL,
    tokens_output integer NOT NULL,
    tokens_cache integer NOT NULL,
    tokens_total integer NOT NULL,
    costo_usd numeric(12,6) NOT NULL,
    request_file character varying(500),
    response_file character varying(500),
    status character varying(20) NOT NULL,
    error_mensaje text,
    latencia_ms integer,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: core_logs_sincronizacion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_logs_sincronizacion (
    id uuid NOT NULL,
    proceso_id uuid NOT NULL,
    fecha_inicio timestamp without time zone NOT NULL,
    fecha_fin timestamp without time zone,
    resultado character varying(20),
    mensaje text,
    registros_procesados integer,
    registros_actualizados integer,
    registros_creados integer,
    registros_errores integer,
    detalle_errores text,
    ejecutado_por character varying(255),
    created_at timestamp without time zone NOT NULL
);


--
-- Name: core_menu_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_menu_items (
    id uuid NOT NULL,
    menu_id uuid NOT NULL,
    codigo character varying(50) NOT NULL,
    nombre character varying(100) NOT NULL,
    icono character varying(50),
    ruta character varying(200),
    orden integer,
    activo boolean,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone
);


--
-- Name: core_menus; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_menus (
    id uuid NOT NULL,
    codigo character varying(50) NOT NULL,
    nombre character varying(100) NOT NULL,
    icono character varying(50),
    orden integer,
    activo boolean,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone
);


--
-- Name: core_notificaciones_internas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_notificaciones_internas (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    usuario_id uuid NOT NULL,
    tipo character varying(30) NOT NULL,
    titulo character varying(160) NOT NULL,
    mensaje text NOT NULL,
    enlace character varying(500),
    origen character varying(100),
    leida_at timestamp without time zone,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: core_oidc_clientes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_oidc_clientes (
    id uuid NOT NULL,
    client_id character varying(100) NOT NULL,
    nombre character varying(150) NOT NULL,
    redirect_uris jsonb NOT NULL,
    scopes character varying(255) NOT NULL,
    secreto_hash character varying(100) NOT NULL,
    secreto_nuevo_hash character varying(100),
    activo boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: core_oidc_codigos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_oidc_codigos (
    id uuid NOT NULL,
    codigo_hash character varying(64) NOT NULL,
    cliente_id uuid NOT NULL,
    usuario_id uuid NOT NULL,
    redirect_uri character varying(500) NOT NULL,
    scope character varying(255) NOT NULL,
    nonce character varying(255) NOT NULL,
    code_challenge character varying(128) NOT NULL,
    expira_at timestamp without time zone NOT NULL,
    usado_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: core_parametros; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_parametros (
    id uuid NOT NULL,
    categoria character varying(100) NOT NULL,
    subcategoria character varying(100),
    nombre character varying(200) NOT NULL,
    key character varying(100) NOT NULL,
    descripcion text,
    valor_default text,
    valor text,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: core_permisos_modulo; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_permisos_modulo (
    id uuid NOT NULL,
    grupo_id uuid NOT NULL,
    modulo character varying(100) NOT NULL,
    tiene_acceso boolean,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    deleted_at timestamp without time zone
);


--
-- Name: core_procesos_sincronizacion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_procesos_sincronizacion (
    id uuid NOT NULL,
    codigo character varying(50) NOT NULL,
    nombre character varying(150) NOT NULL,
    descripcion text,
    tipo_origen character varying(50) NOT NULL,
    configuracion text,
    query_sql text,
    activo boolean,
    ultima_ejecucion timestamp without time zone,
    ultimo_resultado character varying(20),
    ultimo_mensaje text,
    registros_procesados integer,
    registros_actualizados integer,
    registros_creados integer,
    registros_errores integer,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: core_schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_schema_migrations (
    id character varying(150) NOT NULL,
    applied_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: core_tareas_corridas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_tareas_corridas (
    id uuid NOT NULL,
    tarea character varying(100) NOT NULL,
    disparo character varying(20) NOT NULL,
    estado character varying(20) NOT NULL,
    solicitada_por character varying(255),
    creada_at timestamp without time zone NOT NULL,
    inicio timestamp without time zone,
    fin timestamp without time zone,
    resultado text,
    error text,
    alerta_enviada boolean NOT NULL,
    CONSTRAINT ck_core_tareas_corridas_disparo CHECK (((disparo)::text = ANY ((ARRAY['programado'::character varying, 'manual'::character varying])::text[]))),
    CONSTRAINT ck_core_tareas_corridas_estado CHECK (((estado)::text = ANY ((ARRAY['pendiente'::character varying, 'en_curso'::character varying, 'ok'::character varying, 'error'::character varying])::text[])))
);


--
-- Name: core_usuario_empresa; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_usuario_empresa (
    usuario_id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    created_at timestamp without time zone
);


--
-- Name: core_usuario_grupo; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_usuario_grupo (
    usuario_id uuid NOT NULL,
    grupo_id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    created_at timestamp without time zone
);


--
-- Name: core_usuarios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_usuarios (
    id uuid NOT NULL,
    email character varying(255) NOT NULL,
    password_hash character varying(255) NOT NULL,
    nombre character varying(100) NOT NULL,
    apellido character varying(100),
    dni integer,
    telefono character varying(20),
    avatar_url character varying(500),
    rol character varying(50) NOT NULL,
    activo boolean NOT NULL,
    requiere_password_change boolean NOT NULL,
    magic_link_token character varying(255),
    magic_link_expires timestamp without time zone,
    totp_secret character varying(255),
    totp_enabled boolean NOT NULL,
    totp_required boolean NOT NULL,
    totp_backup_codes character varying(1000),
    ultimo_login timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    deleted_at timestamp without time zone,
    email_secundario character varying(255)
);


--
-- Name: core_webex_oauth_tokens; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.core_webex_oauth_tokens (
    id uuid NOT NULL,
    proposito character varying(50) NOT NULL,
    access_token text,
    refresh_token text,
    expires_at timestamp without time zone,
    refresh_expires_at timestamp without time zone,
    account_email character varying(255),
    account_nombre character varying(255),
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: hrbp_entregas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hrbp_entregas (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    item_tipo_id uuid NOT NULL,
    empleado_id uuid NOT NULL,
    hrbp_usuario_id uuid NOT NULL,
    cantidad integer NOT NULL,
    observaciones text,
    fecha_entrega timestamp without time zone NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: hrbp_item_tipos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hrbp_item_tipos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    descripcion character varying(255),
    stock_actual integer NOT NULL,
    stock_minimo integer NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: innovacion_certificaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.innovacion_certificaciones (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    empleado_id uuid NOT NULL,
    tipo_certificacion character varying(30) NOT NULL,
    estado character varying(20) NOT NULL,
    titulo character varying(200),
    descripcion text,
    repo_presentacion character varying(500),
    repo_demo character varying(500),
    tematica character varying(200),
    tecnologias character varying[],
    fecha_presentacion date,
    fecha_aprobacion date,
    cert_noncode_origen character varying(20),
    cert_noncode_imagen character varying(500),
    cert_noncode_fecha date,
    cert_noncode_plan character varying(500),
    cert_n8n_origen character varying(20),
    cert_n8n_imagen character varying(500),
    cert_n8n_fecha date,
    cert_n8n_plan character varying(500),
    cert_ruta1_imagen character varying(500),
    cert_ruta1_fecha date,
    cert_ruta2_imagen character varying(500),
    cert_ruta2_fecha date,
    cert_ruta3_imagen character varying(500),
    cert_ruta3_fecha date,
    progreso_completados character varying(10),
    porcentaje_avance character varying(10),
    fecha_registro timestamp without time zone,
    fecha_en_progreso timestamp without time zone,
    fecha_en_presentacion timestamp without time zone,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: innovacion_evento_asistencia; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.innovacion_evento_asistencia (
    evento_id uuid NOT NULL,
    empleado_id uuid NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: innovacion_eventos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.innovacion_eventos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(200) NOT NULL,
    fecha date NOT NULL,
    duenio character varying(100),
    tags character varying[],
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: innovacion_herramientas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.innovacion_herramientas (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(150) NOT NULL,
    nombre_normalizado character varying(150) NOT NULL,
    proveedor_id uuid,
    costo_referencia numeric(10,2),
    moneda character varying(3) NOT NULL,
    activo boolean NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: innovacion_licencias; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.innovacion_licencias (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nro_pedido_compra character varying(50),
    costo_mensual numeric(10,2),
    moneda character varying(3) NOT NULL,
    fecha_inicio date NOT NULL,
    fecha_fin date,
    empleado_id uuid NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    herramienta_id uuid NOT NULL,
    activa boolean NOT NULL
);


--
-- Name: innovacion_proveedores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.innovacion_proveedores (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(150) NOT NULL,
    nombre_normalizado character varying(150) NOT NULL,
    activo boolean NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: nomina_carreras; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nomina_carreras (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(150) NOT NULL,
    descripcion character varying(255),
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: nomina_categorias; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nomina_categorias (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    descripcion character varying(255),
    departamento_id uuid,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: nomina_departamentos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nomina_departamentos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    descripcion character varying(255),
    manager_id uuid,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: nomina_empleados; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nomina_empleados (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    codigo character varying(50) NOT NULL,
    cuil bigint NOT NULL,
    apellido character varying(100) NOT NULL,
    nombre character varying(100) NOT NULL,
    fecha_nacimiento date,
    dni integer NOT NULL,
    genero character varying(20),
    nacionalidad character varying(50),
    estado_civil character varying(30),
    nivel_estudio character varying(50),
    carrera_id uuid,
    telefono_personal character varying(30),
    email_personal character varying(255),
    dir_laboral_pais character varying(50),
    dir_laboral_provincia character varying(50),
    dir_laboral_localidad character varying(100),
    dir_laboral_codigo_postal character varying(10),
    dir_laboral_barrio character varying(100),
    dir_laboral_calle character varying(150),
    dir_laboral_numero character varying(20),
    dir_laboral_piso character varying(10),
    dir_laboral_departamento character varying(10),
    usar_direccion_laboral boolean,
    dir_obsequios_pais character varying(50),
    dir_obsequios_provincia character varying(50),
    dir_obsequios_localidad character varying(100),
    dir_obsequios_codigo_postal character varying(10),
    dir_obsequios_barrio character varying(100),
    dir_obsequios_calle character varying(150),
    dir_obsequios_numero character varying(20),
    dir_obsequios_piso character varying(10),
    dir_obsequios_departamento character varying(10),
    preferencia_alimentaria character varying(100),
    instrucciones_entrega character varying(500),
    contacto_emergencia character varying(100),
    numero_emergencia character varying(30),
    parentesco character varying(50),
    fecha_alta date,
    fecha_baja date,
    motivo_baja character varying(100),
    email_corporativo character varying(255),
    departamento_id uuid,
    perfil_id uuid,
    hrbp_id uuid,
    seniority character varying(50),
    puesto character varying(150),
    foto character varying(500),
    activo boolean,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: nomina_perfiles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.nomina_perfiles (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    tipo character varying(50),
    categoria_id uuid,
    descripcion character varying(255),
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: notificaciones_log; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.notificaciones_log (
    id uuid NOT NULL,
    empresa_id uuid,
    tipo character varying(50) NOT NULL,
    fecha_evento date NOT NULL,
    empleado_id uuid,
    empleado_nombre character varying(255),
    empleado_email character varying(255),
    estado character varying(20) NOT NULL,
    contexto_presentacion text,
    mensaje_generado text,
    llm_request_id character varying(64),
    webex_message_id character varying(255),
    error_detalle text,
    enviado_at timestamp without time zone,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: operaciones_equipo_integrantes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.operaciones_equipo_integrantes (
    equipo_id uuid NOT NULL,
    empleado_id uuid NOT NULL,
    created_at timestamp without time zone NOT NULL
);


--
-- Name: operaciones_equipos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.operaciones_equipos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    cliente_id uuid,
    lider_id uuid,
    activo boolean NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: proveedores_auditoria; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proveedores_auditoria (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    fecha_hora timestamp without time zone NOT NULL,
    usuario_id uuid,
    usuario_email character varying(255),
    ip character varying(45),
    user_agent character varying(500),
    entidad character varying(20) NOT NULL,
    entidad_id uuid NOT NULL,
    evaluacion_id uuid,
    accion character varying(30) NOT NULL,
    antes jsonb,
    despues jsonb,
    CONSTRAINT ck_proveedores_auditoria_entidad CHECK (((entidad)::text = ANY ((ARRAY['proveedor'::character varying, 'contacto'::character varying, 'oficina'::character varying, 'documento'::character varying, 'configuracion'::character varying, 'evaluacion'::character varying, 'item'::character varying, 'aviso'::character varying])::text[])))
);


--
-- Name: proveedores_avisos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proveedores_avisos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    evaluacion_id uuid NOT NULL,
    fecha_hora timestamp without time zone NOT NULL,
    fecha_local date NOT NULL,
    motivo character varying(15) NOT NULL,
    canal character varying(15) NOT NULL,
    empleado_id uuid,
    destino character varying(255) NOT NULL,
    cc text,
    pendientes integer NOT NULL,
    enviado boolean NOT NULL,
    error text,
    enviado_por uuid,
    CONSTRAINT ck_proveedores_aviso_canal CHECK (((canal)::text = ANY ((ARRAY['email'::character varying, 'webex_personal'::character varying, 'webex_canal'::character varying])::text[]))),
    CONSTRAINT ck_proveedores_aviso_motivo CHECK (((motivo)::text = ANY ((ARRAY['apertura'::character varying, 'recordatorio'::character varying, 'previo_cierre'::character varying, 'manual'::character varying])::text[])))
);


--
-- Name: proveedores_configuracion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proveedores_configuracion (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    sheet_url character varying(500),
    sheet_hoja character varying(100) NOT NULL,
    recordar_cada_dias smallint,
    aviso_apertura boolean NOT NULL,
    aviso_previo_cierre boolean NOT NULL,
    hora_envio time without time zone DEFAULT '09:00:00'::time without time zone NOT NULL,
    canal_email boolean NOT NULL,
    email_cc text,
    canal_webex_personal boolean NOT NULL,
    canal_webex_canal boolean NOT NULL,
    webex_room_id character varying(255),
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    auto_generar boolean DEFAULT false NOT NULL,
    auto_inicio_dia smallint,
    auto_inicio_mes smallint,
    auto_fin_dia smallint,
    auto_fin_mes smallint,
    auto_ultimo_periodo character varying(20),
    CONSTRAINT ck_proveedores_config_auto CHECK (((NOT auto_generar) OR ((auto_inicio_dia IS NOT NULL) AND (auto_inicio_mes IS NOT NULL) AND (auto_fin_dia IS NOT NULL) AND (auto_fin_mes IS NOT NULL)))),
    CONSTRAINT ck_proveedores_config_auto_rangos CHECK ((((auto_inicio_dia >= 1) AND (auto_inicio_dia <= 31)) AND ((auto_fin_dia >= 1) AND (auto_fin_dia <= 31)) AND ((auto_inicio_mes >= 1) AND (auto_inicio_mes <= 12)) AND ((auto_fin_mes >= 1) AND (auto_fin_mes <= 12)))),
    CONSTRAINT ck_proveedores_config_recordar CHECK ((recordar_cada_dias = ANY (ARRAY[1, 2]))),
    CONSTRAINT ck_proveedores_config_room CHECK (((NOT canal_webex_canal) OR (webex_room_id IS NOT NULL)))
);


--
-- Name: proveedores_contactos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proveedores_contactos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    proveedor_id uuid NOT NULL,
    oficina_id uuid,
    nombre character varying(150) NOT NULL,
    apellido character varying(100),
    cargo character varying(150),
    telefono character varying(30),
    email character varying(255),
    es_principal boolean NOT NULL,
    notas character varying(500),
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    deleted_at timestamp without time zone
);


--
-- Name: proveedores_documentos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proveedores_documentos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    proveedor_id uuid NOT NULL,
    nombre character varying(255) NOT NULL,
    clave character varying(500) NOT NULL,
    tipo_mime character varying(100) NOT NULL,
    tamano integer NOT NULL,
    miniatura_clave character varying(500),
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    deleted_at timestamp without time zone
);


--
-- Name: proveedores_evaluacion_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proveedores_evaluacion_items (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    evaluacion_id uuid NOT NULL,
    proveedor_id uuid NOT NULL,
    evaluador_empleado_id uuid,
    incidentes character varying(5),
    mal_manejo character varying(5),
    evidencia_incidentes text,
    evidencia_mal_manejo text,
    evaluado_at timestamp without time zone,
    evaluado_por uuid,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    deleted_at timestamp without time zone,
    con_hallazgo boolean GENERATED ALWAYS AS ((COALESCE(((incidentes)::text = 'Si'::text), false) OR COALESCE(((mal_manejo)::text = 'Si'::text), false))) STORED,
    CONSTRAINT ck_proveedores_item_incidentes CHECK (((incidentes)::text = ANY ((ARRAY['Si'::character varying, 'No'::character varying, 'N/A'::character varying])::text[]))),
    CONSTRAINT ck_proveedores_item_mal_manejo CHECK (((mal_manejo)::text = ANY ((ARRAY['Si'::character varying, 'No'::character varying])::text[])))
);


--
-- Name: proveedores_evaluaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proveedores_evaluaciones (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    periodo character varying(20) NOT NULL,
    fecha_apertura date NOT NULL,
    fecha_cierre date NOT NULL,
    reemplazada_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    deleted_at timestamp without time zone,
    CONSTRAINT ck_proveedores_evaluacion_fechas CHECK ((fecha_cierre >= fecha_apertura))
);


--
-- Name: proveedores_importacion_filas; Type: TABLE; Schema: public; Owner: -
--

CREATE UNLOGGED TABLE public.proveedores_importacion_filas (
    id uuid NOT NULL,
    importacion_id uuid NOT NULL,
    fila_sheet integer NOT NULL,
    nombre character varying(200) NOT NULL,
    referente_sheet character varying(200),
    accion character varying(20) NOT NULL,
    proveedor_id uuid,
    referente_anterior_id uuid,
    referente_nuevo_id uuid,
    servicio_provisto text,
    tipo_informacion text,
    acuerdo_servicio character varying(5),
    politica_nda text,
    confirmar boolean NOT NULL,
    motivo text,
    CONSTRAINT ck_proveedores_importacion_accion CHECK (((accion)::text = ANY ((ARRAY['alta'::character varying, 'sin_cambios'::character varying, 'cambio_referente'::character varying, 'rechazada'::character varying])::text[])))
);


--
-- Name: proveedores_importaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE UNLOGGED TABLE public.proveedores_importaciones (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    evaluacion_id uuid NOT NULL,
    creada_at timestamp without time zone NOT NULL,
    creada_por uuid
);


--
-- Name: proveedores_oficinas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proveedores_oficinas (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    proveedor_id uuid NOT NULL,
    nombre_oficina character varying(100),
    calle character varying(200) NOT NULL,
    numero character varying(20),
    piso character varying(20),
    departamento character varying(20),
    localidad character varying(100) NOT NULL,
    provincia character varying(100),
    pais character varying(100) NOT NULL,
    codigo_postal character varying(10),
    es_legal boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    deleted_at timestamp without time zone
);


--
-- Name: proveedores_proveedores; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proveedores_proveedores (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(200) NOT NULL,
    razon_social character varying(200),
    cuit character varying(13),
    responsabilidad_afip character varying(50),
    nro_ingresos_brutos character varying(50),
    tipo character varying(20) NOT NULL,
    referente_empleado_id uuid,
    servicio_provisto text,
    tipo_informacion text,
    email character varying(255),
    telefono_whatsapp character varying(20),
    pagina_web character varying(500),
    acuerdo_servicio character varying(5),
    politica_nda text,
    politica_nda_archivo character varying(500),
    politica_nda_archivo_nombre character varying(255),
    observaciones text,
    activo boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    deleted_at timestamp without time zone,
    CONSTRAINT ck_proveedores_acuerdo CHECK (((acuerdo_servicio)::text = ANY ((ARRAY['Si'::character varying, 'No'::character varying])::text[]))),
    CONSTRAINT ck_proveedores_iva CHECK (((responsabilidad_afip)::text = ANY ((ARRAY['Responsable Inscripto'::character varying, 'Sujeto Exento'::character varying, 'Consumidor Final'::character varying, 'Responsable Monotributo'::character varying, 'Proveedor del Exterior'::character varying, 'Sujeto No Categorizado'::character varying])::text[]))),
    CONSTRAINT ck_proveedores_tipo CHECK (((tipo)::text = ANY ((ARRAY['proveedor'::character varying, 'herramienta'::character varying, 'sin_clasificar'::character varying])::text[])))
);


--
-- Name: recibos_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recibos_logs (
    id uuid NOT NULL,
    recibo_id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    accion character varying(50) NOT NULL,
    usuario_email character varying(255),
    usuario_nombre character varying(200),
    ip character varying(45),
    detalle character varying(500),
    created_at timestamp without time zone NOT NULL
);


--
-- Name: recibos_logs_bkp_20260722; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recibos_logs_bkp_20260722 (
    id uuid,
    recibo_id uuid,
    empresa_id uuid,
    accion character varying(50),
    usuario_email character varying(255),
    usuario_nombre character varying(200),
    ip character varying(45),
    detalle character varying(500),
    created_at timestamp without time zone
);


--
-- Name: recibos_lotes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recibos_lotes (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    periodo character varying(7) NOT NULL,
    tipo_liquidacion character varying(50) NOT NULL,
    estado character varying(30) NOT NULL,
    archivo_original character varying(500) NOT NULL,
    archivo_nombre character varying(255) NOT NULL,
    total_paginas integer,
    total_recibos integer,
    total_errores integer,
    errores_detalle json,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: recibos_lotes_bkp_20260722; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recibos_lotes_bkp_20260722 (
    id uuid,
    empresa_id uuid,
    periodo character varying(7),
    tipo_liquidacion character varying(50),
    estado character varying(30),
    archivo_original character varying(500),
    archivo_nombre character varying(255),
    total_paginas integer,
    total_recibos integer,
    total_errores integer,
    errores_detalle json,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    updated_by character varying(255)
);


--
-- Name: recibos_recibos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recibos_recibos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    lote_id uuid NOT NULL,
    empleado_id uuid,
    cuil_extraido bigint NOT NULL,
    archivo_original character varying(500) NOT NULL,
    archivo_duplicado character varying(500),
    archivo_firmado character varying(500),
    estado character varying(20) NOT NULL,
    pagina_original integer NOT NULL,
    pagina_duplicado integer,
    fecha_firma timestamp without time zone,
    ip_firma character varying(45),
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: recibos_recibos_bkp_20260722; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.recibos_recibos_bkp_20260722 (
    id uuid,
    empresa_id uuid,
    lote_id uuid,
    empleado_id uuid,
    cuil_extraido bigint,
    archivo_original character varying(500),
    archivo_duplicado character varying(500),
    archivo_firmado character varying(500),
    estado character varying(20),
    pagina_original integer,
    pagina_duplicado integer,
    fecha_firma timestamp without time zone,
    ip_firma character varying(45),
    deleted_at timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    updated_by character varying(255)
);


--
-- Name: soporte_activos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_activos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    clase_activo character varying(30) NOT NULL,
    nombre character varying(200) NOT NULL,
    tipo_id uuid NOT NULL,
    marca_id uuid,
    modelo character varying(100),
    numero_serie character varying(100),
    numero_inventario character varying(50),
    estado character varying(50),
    asignado_id uuid,
    fecha_asignacion timestamp without time zone,
    fecha_compra timestamp without time zone,
    fecha_fin_garantia timestamp without time zone,
    notas text,
    fecha_ultimo_mantenimiento timestamp without time zone,
    matriz_estado_id uuid,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    deleted_at timestamp without time zone
);


--
-- Name: soporte_activos_especificaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_activos_especificaciones (
    id uuid NOT NULL,
    procesador character varying(150),
    memoria character varying(50),
    disco_principal character varying(100),
    disco_secundario character varying(100),
    mac_ethernet character varying(100),
    mac_wifi character varying(100)
);


--
-- Name: soporte_activos_marcas; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_activos_marcas (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: soporte_activos_tipos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_activos_tipos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    clave character varying(100) NOT NULL,
    requiere_especificaciones boolean NOT NULL,
    frecuencia_mantenimiento_meses integer,
    activo boolean NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: soporte_categorias; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_categorias (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre_display character varying(100) NOT NULL,
    nombre_normalizado character varying(100) NOT NULL,
    tipo_ticket_asociado character varying(20) NOT NULL,
    departamento_id uuid,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: soporte_evidencias; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_evidencias (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    url character varying(500) NOT NULL,
    tipo character varying(50) NOT NULL,
    categoria character varying(50) NOT NULL,
    ticket_id uuid,
    activo_id uuid,
    historial_id uuid,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_by character varying(255)
);


--
-- Name: soporte_historial_activo; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_historial_activo (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    activo_id uuid,
    colaborador_id uuid,
    responsable_id uuid,
    fecha_hora timestamp without time zone,
    tipo_evento character varying(50),
    notas_adicionales text,
    matriz_estado_id uuid,
    pedido_compra_id uuid,
    created_at timestamp without time zone,
    created_by character varying(255),
    updated_at timestamp without time zone,
    updated_by character varying(255)
);


--
-- Name: soporte_insumos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_insumos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(150) NOT NULL,
    descripcion character varying(255),
    stock_actual integer,
    stock_minimo integer,
    unidad_medida character varying(20),
    categoria_id uuid,
    deleted_at timestamp without time zone,
    deleted_by character varying(255),
    created_at timestamp without time zone,
    created_by character varying(255),
    updated_at timestamp without time zone,
    updated_by character varying(255)
);


--
-- Name: soporte_mantenimiento_evento; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_mantenimiento_evento (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    activo_id uuid,
    asignado_id uuid,
    fecha_ejecucion timestamp without time zone,
    estado_anterior character varying(20),
    estado_nuevo character varying(20),
    fecha_hora timestamp without time zone,
    notas text,
    created_at timestamp without time zone,
    created_by character varying(255),
    updated_at timestamp without time zone,
    updated_by character varying(255)
);


--
-- Name: soporte_matriz_estado; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_matriz_estado (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    pantalla character varying(50),
    teclado character varying(50),
    bateria character varying(50),
    carcasa_superior character varying(50),
    carcasa_inferior character varying(50),
    touchpad character varying(50),
    puertos character varying(50),
    cargador character varying(50),
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_by character varying(255),
    deleted_at timestamp without time zone,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: soporte_movimientos_insumos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_movimientos_insumos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    insumo_id uuid NOT NULL,
    tipo character varying(20) NOT NULL,
    cantidad integer NOT NULL,
    activo_id uuid,
    empleado_id uuid,
    empleado_asignador_id uuid,
    pedido_compra_id uuid,
    motivo character varying(255),
    fecha_movimiento timestamp without time zone,
    created_at timestamp without time zone,
    created_by character varying(255),
    updated_by character varying(255)
);


--
-- Name: soporte_pedidos_aprobaciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_pedidos_aprobaciones (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    pedido_id uuid,
    departamento_id uuid,
    aprobador_id uuid,
    estado character varying(50),
    fecha_decision timestamp without time zone,
    observaciones text,
    orden_aprobacion integer,
    created_at timestamp without time zone,
    created_by character varying(255),
    updated_by character varying(255)
);


--
-- Name: soporte_pedidos_compra; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_pedidos_compra (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    numero character varying(50) NOT NULL,
    tipo_pedido character varying(20),
    descripcion text,
    monto_estimado numeric(12,2),
    monto_final numeric(12,2),
    estado_id uuid,
    fecha_solicitud timestamp without time zone,
    fecha_recepcion timestamp without time zone,
    solicitante_id uuid,
    ticket_id uuid,
    insumo_id uuid,
    cantidad_solicitada integer,
    cantidad_recibida integer,
    notas text,
    deleted_at timestamp without time zone,
    requiere_doble_aprobacion boolean NOT NULL,
    created_at timestamp without time zone,
    created_by character varying(255),
    updated_at timestamp without time zone,
    updated_by character varying(255)
);


--
-- Name: soporte_pedidos_estados; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_pedidos_estados (
    id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    clave character varying(100) NOT NULL,
    color character varying(50),
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: soporte_pedidos_presupuestos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_pedidos_presupuestos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    pedido_id uuid,
    proveedor character varying(200),
    url_archivo character varying(500),
    articulo_descripcion text,
    monto numeric(12,2),
    es_seleccionado boolean,
    es_obligatorio boolean,
    created_at timestamp without time zone,
    created_by character varying(255),
    updated_by character varying(255)
);


--
-- Name: soporte_sistemas_disponibles; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_sistemas_disponibles (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    clave character varying(100) NOT NULL,
    label character varying(255) NOT NULL,
    orden integer NOT NULL,
    tipo character varying(10) NOT NULL,
    clave_alta_ref character varying(100),
    activo boolean NOT NULL,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: soporte_subcategorias; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_subcategorias (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    categoria_id uuid NOT NULL,
    nombre_display character varying(100) NOT NULL,
    nombre_normalizado character varying(100) NOT NULL,
    tipo_ticket_asociado character varying(20) NOT NULL,
    departamento_id uuid,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: soporte_ticket_checklist_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_ticket_checklist_items (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    sistema_id uuid,
    item_clave character varying(100) NOT NULL,
    item_label character varying(255) NOT NULL,
    completado boolean NOT NULL,
    completado_por character varying(255),
    completado_at timestamp without time zone,
    orden integer NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    updated_by character varying(255)
);


--
-- Name: soporte_tickets; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_tickets (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    numero integer NOT NULL,
    tipo_ticket character varying(20) NOT NULL,
    titulo character varying(200) NOT NULL,
    descripcion text,
    estado_id uuid NOT NULL,
    prioridad character varying(50) NOT NULL,
    subcategoria_id uuid NOT NULL,
    es_falla boolean NOT NULL,
    solicitante_id uuid NOT NULL,
    asignado_id uuid,
    resolucion text,
    fecha_inicio timestamp without time zone,
    fecha_resolucion timestamp without time zone,
    fecha_cierre timestamp without time zone,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: soporte_tickets_alta_baja; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_tickets_alta_baja (
    id uuid NOT NULL,
    colaborador_id uuid NOT NULL,
    tipo_operacion character varying(10) NOT NULL,
    entrega_kit_bienvenida boolean,
    activo_id uuid,
    matriz_estado_id uuid,
    modalidad_trabajo character varying(30),
    requiere_nextcloud boolean,
    listas_correo text,
    necesita_computadora boolean,
    gama_computadora character varying(50),
    cliente_servicio character varying(200)
);


--
-- Name: soporte_tickets_estados; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_tickets_estados (
    id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    clave character varying(100) NOT NULL,
    color character varying(50),
    created_at timestamp without time zone NOT NULL,
    created_by character varying(255),
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: soporte_tickets_insumos; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_tickets_insumos (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    ticket_id uuid NOT NULL,
    insumo_id uuid NOT NULL,
    cantidad integer,
    costo_unitario numeric(10,2),
    generar_pedido_compra boolean,
    movimiento_insumo_id uuid,
    pedido_compra_id uuid,
    created_at timestamp without time zone,
    created_by character varying(255),
    updated_by character varying(255)
);


--
-- Name: soporte_tickets_mantenimiento; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_tickets_mantenimiento (
    id uuid NOT NULL,
    activo_id uuid NOT NULL,
    mantenimiento_id uuid,
    detalle_tecnico text,
    is_preventivo boolean,
    fecha_programada timestamp without time zone,
    se_realizo boolean
);


--
-- Name: soporte_tickets_reparacion; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.soporte_tickets_reparacion (
    id uuid NOT NULL,
    activo_id uuid NOT NULL,
    diagnostico text,
    solucion text,
    costo_estimado numeric(10,2),
    costo_total_final numeric(10,2),
    matriz_entrada_id uuid,
    matriz_salida_id uuid
);


--
-- Name: starmiles_canjes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.starmiles_canjes (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    item_id uuid NOT NULL,
    empleado_id uuid NOT NULL,
    cantidad integer NOT NULL,
    star_miles_total integer NOT NULL,
    mercadolibre_url character varying(500),
    mercadolibre_precio numeric(12,2),
    estado character varying(20) NOT NULL,
    fecha_solicitud timestamp without time zone NOT NULL,
    fecha_aprobacion timestamp without time zone,
    fecha_entrega timestamp without time zone,
    fecha_rechazo timestamp without time zone,
    aprobador_id uuid,
    comentario text,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: starmiles_categorias; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.starmiles_categorias (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    nombre character varying(100) NOT NULL,
    descripcion character varying(255),
    color character varying(7),
    icono character varying(50),
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: starmiles_contenido_cms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.starmiles_contenido_cms (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    tipo character varying(30) NOT NULL,
    titulo character varying(200) NOT NULL,
    contenido text,
    imagen_url character varying(500),
    empleado_id uuid,
    orden integer,
    visible boolean,
    fecha_publicacion timestamp without time zone,
    fecha_expiracion timestamp without time zone,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: starmiles_desafios; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.starmiles_desafios (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    categoria_id uuid,
    nombre character varying(150) NOT NULL,
    descripcion text,
    alcance character varying(255),
    star_miles integer NOT NULL,
    fecha_inicio date,
    fecha_vencimiento date,
    activo boolean,
    imagen_url character varying(500),
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255),
    inscripcion_unica_por_empleado boolean DEFAULT false NOT NULL
);


--
-- Name: starmiles_empleados; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.starmiles_empleados (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    empleado_id uuid NOT NULL,
    millas_historicas integer NOT NULL,
    millas_disponibles integer NOT NULL,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: starmiles_inscripciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.starmiles_inscripciones (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    desafio_id uuid NOT NULL,
    empleado_id uuid NOT NULL,
    estado character varying(20) NOT NULL,
    fecha_solicitud timestamp without time zone NOT NULL,
    fecha_aprobacion timestamp without time zone,
    fecha_finalizacion timestamp without time zone,
    fecha_rechazo timestamp without time zone,
    aprobador_id uuid,
    comentario_solicitud text,
    comentario_aprobador text,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL
);


--
-- Name: starmiles_items_canje; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.starmiles_items_canje (
    id uuid NOT NULL,
    empresa_id uuid NOT NULL,
    tipo character varying(20) NOT NULL,
    nombre character varying(150) NOT NULL,
    descripcion text,
    star_miles_costo integer,
    stock integer,
    imagen_url character varying(500),
    activo boolean,
    deleted_at timestamp without time zone,
    created_at timestamp without time zone NOT NULL,
    updated_at timestamp without time zone NOT NULL,
    updated_by character varying(255)
);


--
-- Name: admin_categorias_cliente admin_categorias_cliente_nombre_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_categorias_cliente
    ADD CONSTRAINT admin_categorias_cliente_nombre_key UNIQUE (nombre);


--
-- Name: admin_categorias_cliente admin_categorias_cliente_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_categorias_cliente
    ADD CONSTRAINT admin_categorias_cliente_pkey PRIMARY KEY (id);


--
-- Name: admin_cliente_categoria admin_cliente_categoria_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_cliente_categoria
    ADD CONSTRAINT admin_cliente_categoria_pkey PRIMARY KEY (cliente_id, categoria_id);


--
-- Name: admin_cliente_domicilios admin_cliente_domicilios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_cliente_domicilios
    ADD CONSTRAINT admin_cliente_domicilios_pkey PRIMARY KEY (id);


--
-- Name: admin_clientes admin_clientes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_clientes
    ADD CONSTRAINT admin_clientes_pkey PRIMARY KEY (id);


--
-- Name: innovacion_licencias admin_licencias_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_licencias
    ADD CONSTRAINT admin_licencias_pkey PRIMARY KEY (id);


--
-- Name: administracion_recibos_export administracion_recibos_export_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.administracion_recibos_export
    ADD CONSTRAINT administracion_recibos_export_pkey PRIMARY KEY (id);


--
-- Name: core_auditoria_log core_auditoria_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_auditoria_log
    ADD CONSTRAINT core_auditoria_log_pkey PRIMARY KEY (id);


--
-- Name: core_empresa_domicilios core_empresa_domicilios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_empresa_domicilios
    ADD CONSTRAINT core_empresa_domicilios_pkey PRIMARY KEY (id);


--
-- Name: core_empresas core_empresas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_empresas
    ADD CONSTRAINT core_empresas_pkey PRIMARY KEY (id);


--
-- Name: core_envios core_envios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_envios
    ADD CONSTRAINT core_envios_pkey PRIMARY KEY (id);


--
-- Name: core_grupo_departamento core_grupo_departamento_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_grupo_departamento
    ADD CONSTRAINT core_grupo_departamento_pkey PRIMARY KEY (grupo_id, departamento_id, empresa_id);


--
-- Name: core_grupo_menu core_grupo_menu_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_grupo_menu
    ADD CONSTRAINT core_grupo_menu_pkey PRIMARY KEY (grupo_id, menu_id);


--
-- Name: core_grupos core_grupos_nombre_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_grupos
    ADD CONSTRAINT core_grupos_nombre_key UNIQUE (nombre);


--
-- Name: core_grupos core_grupos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_grupos
    ADD CONSTRAINT core_grupos_pkey PRIMARY KEY (id);


--
-- Name: core_llm_requests core_llm_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_llm_requests
    ADD CONSTRAINT core_llm_requests_pkey PRIMARY KEY (id);


--
-- Name: core_logs_sincronizacion core_logs_sincronizacion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_logs_sincronizacion
    ADD CONSTRAINT core_logs_sincronizacion_pkey PRIMARY KEY (id);


--
-- Name: core_menu_items core_menu_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_menu_items
    ADD CONSTRAINT core_menu_items_pkey PRIMARY KEY (id);


--
-- Name: core_menus core_menus_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_menus
    ADD CONSTRAINT core_menus_codigo_key UNIQUE (codigo);


--
-- Name: core_menus core_menus_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_menus
    ADD CONSTRAINT core_menus_pkey PRIMARY KEY (id);


--
-- Name: core_notificaciones_internas core_notificaciones_internas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_notificaciones_internas
    ADD CONSTRAINT core_notificaciones_internas_pkey PRIMARY KEY (id);


--
-- Name: core_oidc_clientes core_oidc_clientes_client_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_oidc_clientes
    ADD CONSTRAINT core_oidc_clientes_client_id_key UNIQUE (client_id);


--
-- Name: core_oidc_clientes core_oidc_clientes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_oidc_clientes
    ADD CONSTRAINT core_oidc_clientes_pkey PRIMARY KEY (id);


--
-- Name: core_oidc_codigos core_oidc_codigos_codigo_hash_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_oidc_codigos
    ADD CONSTRAINT core_oidc_codigos_codigo_hash_key UNIQUE (codigo_hash);


--
-- Name: core_oidc_codigos core_oidc_codigos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_oidc_codigos
    ADD CONSTRAINT core_oidc_codigos_pkey PRIMARY KEY (id);


--
-- Name: core_parametros core_parametros_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_parametros
    ADD CONSTRAINT core_parametros_pkey PRIMARY KEY (id);


--
-- Name: core_permisos_modulo core_permisos_modulo_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_permisos_modulo
    ADD CONSTRAINT core_permisos_modulo_pkey PRIMARY KEY (id);


--
-- Name: core_procesos_sincronizacion core_procesos_sincronizacion_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_procesos_sincronizacion
    ADD CONSTRAINT core_procesos_sincronizacion_codigo_key UNIQUE (codigo);


--
-- Name: core_procesos_sincronizacion core_procesos_sincronizacion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_procesos_sincronizacion
    ADD CONSTRAINT core_procesos_sincronizacion_pkey PRIMARY KEY (id);


--
-- Name: core_schema_migrations core_schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_schema_migrations
    ADD CONSTRAINT core_schema_migrations_pkey PRIMARY KEY (id);


--
-- Name: core_tareas_corridas core_tareas_corridas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_tareas_corridas
    ADD CONSTRAINT core_tareas_corridas_pkey PRIMARY KEY (id);


--
-- Name: core_usuario_empresa core_usuario_empresa_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_usuario_empresa
    ADD CONSTRAINT core_usuario_empresa_pkey PRIMARY KEY (usuario_id, empresa_id);


--
-- Name: core_usuario_grupo core_usuario_grupo_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_usuario_grupo
    ADD CONSTRAINT core_usuario_grupo_pkey PRIMARY KEY (usuario_id, grupo_id, empresa_id);


--
-- Name: core_usuarios core_usuarios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_usuarios
    ADD CONSTRAINT core_usuarios_pkey PRIMARY KEY (id);


--
-- Name: core_webex_oauth_tokens core_webex_oauth_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_webex_oauth_tokens
    ADD CONSTRAINT core_webex_oauth_tokens_pkey PRIMARY KEY (id);


--
-- Name: core_webex_oauth_tokens core_webex_oauth_tokens_proposito_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_webex_oauth_tokens
    ADD CONSTRAINT core_webex_oauth_tokens_proposito_key UNIQUE (proposito);


--
-- Name: hrbp_entregas hrbp_entregas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hrbp_entregas
    ADD CONSTRAINT hrbp_entregas_pkey PRIMARY KEY (id);


--
-- Name: hrbp_item_tipos hrbp_item_tipos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hrbp_item_tipos
    ADD CONSTRAINT hrbp_item_tipos_pkey PRIMARY KEY (id);


--
-- Name: innovacion_certificaciones innovacion_certificaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_certificaciones
    ADD CONSTRAINT innovacion_certificaciones_pkey PRIMARY KEY (id);


--
-- Name: innovacion_evento_asistencia innovacion_evento_asistencia_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_evento_asistencia
    ADD CONSTRAINT innovacion_evento_asistencia_pkey PRIMARY KEY (evento_id, empleado_id);


--
-- Name: innovacion_eventos innovacion_eventos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_eventos
    ADD CONSTRAINT innovacion_eventos_pkey PRIMARY KEY (id);


--
-- Name: innovacion_herramientas innovacion_herramientas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_herramientas
    ADD CONSTRAINT innovacion_herramientas_pkey PRIMARY KEY (id);


--
-- Name: innovacion_proveedores innovacion_proveedores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_proveedores
    ADD CONSTRAINT innovacion_proveedores_pkey PRIMARY KEY (id);


--
-- Name: nomina_carreras nomina_carreras_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_carreras
    ADD CONSTRAINT nomina_carreras_pkey PRIMARY KEY (id);


--
-- Name: nomina_categorias nomina_categorias_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_categorias
    ADD CONSTRAINT nomina_categorias_pkey PRIMARY KEY (id);


--
-- Name: nomina_departamentos nomina_departamentos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_departamentos
    ADD CONSTRAINT nomina_departamentos_pkey PRIMARY KEY (id);


--
-- Name: nomina_empleados nomina_empleados_codigo_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_empleados
    ADD CONSTRAINT nomina_empleados_codigo_key UNIQUE (codigo);


--
-- Name: nomina_empleados nomina_empleados_cuil_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_empleados
    ADD CONSTRAINT nomina_empleados_cuil_key UNIQUE (cuil);


--
-- Name: nomina_empleados nomina_empleados_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_empleados
    ADD CONSTRAINT nomina_empleados_pkey PRIMARY KEY (id);


--
-- Name: nomina_perfiles nomina_perfiles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_perfiles
    ADD CONSTRAINT nomina_perfiles_pkey PRIMARY KEY (id);


--
-- Name: notificaciones_log notificaciones_log_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.notificaciones_log
    ADD CONSTRAINT notificaciones_log_pkey PRIMARY KEY (id);


--
-- Name: operaciones_equipo_integrantes operaciones_equipo_integrantes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operaciones_equipo_integrantes
    ADD CONSTRAINT operaciones_equipo_integrantes_pkey PRIMARY KEY (equipo_id, empleado_id);


--
-- Name: operaciones_equipos operaciones_equipos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operaciones_equipos
    ADD CONSTRAINT operaciones_equipos_pkey PRIMARY KEY (id);


--
-- Name: proveedores_auditoria proveedores_auditoria_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_auditoria
    ADD CONSTRAINT proveedores_auditoria_pkey PRIMARY KEY (id);


--
-- Name: proveedores_avisos proveedores_avisos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_avisos
    ADD CONSTRAINT proveedores_avisos_pkey PRIMARY KEY (id);


--
-- Name: proveedores_configuracion proveedores_configuracion_empresa_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_configuracion
    ADD CONSTRAINT proveedores_configuracion_empresa_id_key UNIQUE (empresa_id);


--
-- Name: proveedores_configuracion proveedores_configuracion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_configuracion
    ADD CONSTRAINT proveedores_configuracion_pkey PRIMARY KEY (id);


--
-- Name: proveedores_contactos proveedores_contactos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_contactos
    ADD CONSTRAINT proveedores_contactos_pkey PRIMARY KEY (id);


--
-- Name: proveedores_documentos proveedores_documentos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_documentos
    ADD CONSTRAINT proveedores_documentos_pkey PRIMARY KEY (id);


--
-- Name: proveedores_evaluacion_items proveedores_evaluacion_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_evaluacion_items
    ADD CONSTRAINT proveedores_evaluacion_items_pkey PRIMARY KEY (id);


--
-- Name: proveedores_evaluaciones proveedores_evaluaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_evaluaciones
    ADD CONSTRAINT proveedores_evaluaciones_pkey PRIMARY KEY (id);


--
-- Name: proveedores_importacion_filas proveedores_importacion_filas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_importacion_filas
    ADD CONSTRAINT proveedores_importacion_filas_pkey PRIMARY KEY (id);


--
-- Name: proveedores_importaciones proveedores_importaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_importaciones
    ADD CONSTRAINT proveedores_importaciones_pkey PRIMARY KEY (id);


--
-- Name: proveedores_oficinas proveedores_oficinas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_oficinas
    ADD CONSTRAINT proveedores_oficinas_pkey PRIMARY KEY (id);


--
-- Name: proveedores_proveedores proveedores_proveedores_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_proveedores
    ADD CONSTRAINT proveedores_proveedores_pkey PRIMARY KEY (id);


--
-- Name: recibos_logs recibos_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recibos_logs
    ADD CONSTRAINT recibos_logs_pkey PRIMARY KEY (id);


--
-- Name: recibos_lotes recibos_lotes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recibos_lotes
    ADD CONSTRAINT recibos_lotes_pkey PRIMARY KEY (id);


--
-- Name: recibos_recibos recibos_recibos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recibos_recibos
    ADD CONSTRAINT recibos_recibos_pkey PRIMARY KEY (id);


--
-- Name: soporte_activos_especificaciones soporte_activos_especificaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos_especificaciones
    ADD CONSTRAINT soporte_activos_especificaciones_pkey PRIMARY KEY (id);


--
-- Name: soporte_activos_marcas soporte_activos_marcas_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos_marcas
    ADD CONSTRAINT soporte_activos_marcas_pkey PRIMARY KEY (id);


--
-- Name: soporte_activos soporte_activos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos
    ADD CONSTRAINT soporte_activos_pkey PRIMARY KEY (id);


--
-- Name: soporte_activos_tipos soporte_activos_tipos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos_tipos
    ADD CONSTRAINT soporte_activos_tipos_pkey PRIMARY KEY (id);


--
-- Name: soporte_categorias soporte_categorias_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_categorias
    ADD CONSTRAINT soporte_categorias_pkey PRIMARY KEY (id);


--
-- Name: soporte_evidencias soporte_evidencias_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_evidencias
    ADD CONSTRAINT soporte_evidencias_pkey PRIMARY KEY (id);


--
-- Name: soporte_historial_activo soporte_historial_activo_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_historial_activo
    ADD CONSTRAINT soporte_historial_activo_pkey PRIMARY KEY (id);


--
-- Name: soporte_insumos soporte_insumos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_insumos
    ADD CONSTRAINT soporte_insumos_pkey PRIMARY KEY (id);


--
-- Name: soporte_mantenimiento_evento soporte_mantenimiento_evento_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_mantenimiento_evento
    ADD CONSTRAINT soporte_mantenimiento_evento_pkey PRIMARY KEY (id);


--
-- Name: soporte_matriz_estado soporte_matriz_estado_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_matriz_estado
    ADD CONSTRAINT soporte_matriz_estado_pkey PRIMARY KEY (id);


--
-- Name: soporte_movimientos_insumos soporte_movimientos_insumos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_movimientos_insumos
    ADD CONSTRAINT soporte_movimientos_insumos_pkey PRIMARY KEY (id);


--
-- Name: soporte_pedidos_aprobaciones soporte_pedidos_aprobaciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_aprobaciones
    ADD CONSTRAINT soporte_pedidos_aprobaciones_pkey PRIMARY KEY (id);


--
-- Name: soporte_pedidos_compra soporte_pedidos_compra_numero_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_compra
    ADD CONSTRAINT soporte_pedidos_compra_numero_key UNIQUE (numero);


--
-- Name: soporte_pedidos_compra soporte_pedidos_compra_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_compra
    ADD CONSTRAINT soporte_pedidos_compra_pkey PRIMARY KEY (id);


--
-- Name: soporte_pedidos_estados soporte_pedidos_estados_clave_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_estados
    ADD CONSTRAINT soporte_pedidos_estados_clave_key UNIQUE (clave);


--
-- Name: soporte_pedidos_estados soporte_pedidos_estados_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_estados
    ADD CONSTRAINT soporte_pedidos_estados_pkey PRIMARY KEY (id);


--
-- Name: soporte_pedidos_presupuestos soporte_pedidos_presupuestos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_presupuestos
    ADD CONSTRAINT soporte_pedidos_presupuestos_pkey PRIMARY KEY (id);


--
-- Name: soporte_sistemas_disponibles soporte_sistemas_disponibles_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_sistemas_disponibles
    ADD CONSTRAINT soporte_sistemas_disponibles_pkey PRIMARY KEY (id);


--
-- Name: soporte_subcategorias soporte_subcategorias_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_subcategorias
    ADD CONSTRAINT soporte_subcategorias_pkey PRIMARY KEY (id);


--
-- Name: soporte_ticket_checklist_items soporte_ticket_checklist_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_ticket_checklist_items
    ADD CONSTRAINT soporte_ticket_checklist_items_pkey PRIMARY KEY (id);


--
-- Name: soporte_tickets_alta_baja soporte_tickets_alta_baja_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_alta_baja
    ADD CONSTRAINT soporte_tickets_alta_baja_pkey PRIMARY KEY (id);


--
-- Name: soporte_tickets_estados soporte_tickets_estados_clave_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_estados
    ADD CONSTRAINT soporte_tickets_estados_clave_key UNIQUE (clave);


--
-- Name: soporte_tickets_estados soporte_tickets_estados_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_estados
    ADD CONSTRAINT soporte_tickets_estados_pkey PRIMARY KEY (id);


--
-- Name: soporte_tickets_insumos soporte_tickets_insumos_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_insumos
    ADD CONSTRAINT soporte_tickets_insumos_pkey PRIMARY KEY (id);


--
-- Name: soporte_tickets_mantenimiento soporte_tickets_mantenimiento_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_mantenimiento
    ADD CONSTRAINT soporte_tickets_mantenimiento_pkey PRIMARY KEY (id);


--
-- Name: soporte_tickets soporte_tickets_numero_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets
    ADD CONSTRAINT soporte_tickets_numero_key UNIQUE (numero);


--
-- Name: soporte_tickets soporte_tickets_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets
    ADD CONSTRAINT soporte_tickets_pkey PRIMARY KEY (id);


--
-- Name: soporte_tickets_reparacion soporte_tickets_reparacion_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_reparacion
    ADD CONSTRAINT soporte_tickets_reparacion_pkey PRIMARY KEY (id);


--
-- Name: starmiles_canjes starmiles_canjes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_canjes
    ADD CONSTRAINT starmiles_canjes_pkey PRIMARY KEY (id);


--
-- Name: starmiles_categorias starmiles_categorias_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_categorias
    ADD CONSTRAINT starmiles_categorias_pkey PRIMARY KEY (id);


--
-- Name: starmiles_contenido_cms starmiles_contenido_cms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_contenido_cms
    ADD CONSTRAINT starmiles_contenido_cms_pkey PRIMARY KEY (id);


--
-- Name: starmiles_desafios starmiles_desafios_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_desafios
    ADD CONSTRAINT starmiles_desafios_pkey PRIMARY KEY (id);


--
-- Name: starmiles_empleados starmiles_empleados_empleado_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_empleados
    ADD CONSTRAINT starmiles_empleados_empleado_id_key UNIQUE (empleado_id);


--
-- Name: starmiles_empleados starmiles_empleados_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_empleados
    ADD CONSTRAINT starmiles_empleados_pkey PRIMARY KEY (id);


--
-- Name: starmiles_inscripciones starmiles_inscripciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_inscripciones
    ADD CONSTRAINT starmiles_inscripciones_pkey PRIMARY KEY (id);


--
-- Name: starmiles_items_canje starmiles_items_canje_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_items_canje
    ADD CONSTRAINT starmiles_items_canje_pkey PRIMARY KEY (id);


--
-- Name: soporte_activos uq_activo_empresa_inventario; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos
    ADD CONSTRAINT uq_activo_empresa_inventario UNIQUE (empresa_id, numero_inventario);


--
-- Name: soporte_activos uq_activo_empresa_serie; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos
    ADD CONSTRAINT uq_activo_empresa_serie UNIQUE (empresa_id, numero_serie);


--
-- Name: soporte_activos_marcas uq_marca_empresa_nombre; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos_marcas
    ADD CONSTRAINT uq_marca_empresa_nombre UNIQUE (empresa_id, nombre);


--
-- Name: soporte_sistemas_disponibles uq_sistema_disponible_empresa_clave; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_sistemas_disponibles
    ADD CONSTRAINT uq_sistema_disponible_empresa_clave UNIQUE (empresa_id, clave);


--
-- Name: soporte_activos_tipos uq_tipo_activo_empresa_clave; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos_tipos
    ADD CONSTRAINT uq_tipo_activo_empresa_clave UNIQUE (empresa_id, clave);


--
-- Name: soporte_activos_tipos uq_tipo_activo_empresa_nombre; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos_tipos
    ADD CONSTRAINT uq_tipo_activo_empresa_nombre UNIQUE (empresa_id, nombre);


--
-- Name: ix_admin_clientes_cuit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_admin_clientes_cuit ON public.admin_clientes USING btree (cuit);


--
-- Name: ix_administracion_recibos_export_cliente; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_administracion_recibos_export_cliente ON public.administracion_recibos_export USING btree (cliente);


--
-- Name: ix_administracion_recibos_export_dni; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_administracion_recibos_export_dni ON public.administracion_recibos_export USING btree (dni);


--
-- Name: ix_auditoria_log_empresa_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auditoria_log_empresa_email ON public.core_auditoria_log USING btree (empresa_id, email_usuario);


--
-- Name: ix_auditoria_log_empresa_fecha; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auditoria_log_empresa_fecha ON public.core_auditoria_log USING btree (empresa_id, fecha_hora);


--
-- Name: ix_auditoria_log_empresa_modulo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_auditoria_log_empresa_modulo ON public.core_auditoria_log USING btree (empresa_id, modulo);


--
-- Name: ix_core_auditoria_log_email_usuario; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_auditoria_log_email_usuario ON public.core_auditoria_log USING btree (email_usuario);


--
-- Name: ix_core_auditoria_log_empresa_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_auditoria_log_empresa_id ON public.core_auditoria_log USING btree (empresa_id);


--
-- Name: ix_core_auditoria_log_fecha_hora; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_auditoria_log_fecha_hora ON public.core_auditoria_log USING btree (fecha_hora);


--
-- Name: ix_core_auditoria_log_modulo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_auditoria_log_modulo ON public.core_auditoria_log USING btree (modulo);


--
-- Name: ix_core_empresas_cuit; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_empresas_cuit ON public.core_empresas USING btree (cuit);


--
-- Name: ix_core_envios_pendientes; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_envios_pendientes ON public.core_envios USING btree (estado, proximo_intento_at);


--
-- Name: ix_core_grupos_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_grupos_deleted_at ON public.core_grupos USING btree (deleted_at);


--
-- Name: ix_core_llm_requests_modulo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_llm_requests_modulo ON public.core_llm_requests USING btree (modulo);


--
-- Name: ix_core_llm_requests_periodo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_llm_requests_periodo ON public.core_llm_requests USING btree (periodo);


--
-- Name: ix_core_menu_items_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_menu_items_deleted_at ON public.core_menu_items USING btree (deleted_at);


--
-- Name: ix_core_menus_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_menus_deleted_at ON public.core_menus USING btree (deleted_at);


--
-- Name: ix_core_oidc_codigos_expira_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_oidc_codigos_expira_at ON public.core_oidc_codigos USING btree (expira_at);


--
-- Name: ix_core_parametros_categoria; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_parametros_categoria ON public.core_parametros USING btree (categoria);


--
-- Name: ix_core_parametros_key; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_core_parametros_key ON public.core_parametros USING btree (key);


--
-- Name: ix_core_permisos_modulo_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_permisos_modulo_deleted_at ON public.core_permisos_modulo USING btree (deleted_at);


--
-- Name: ix_core_tareas_corridas_estado; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_tareas_corridas_estado ON public.core_tareas_corridas USING btree (estado);


--
-- Name: ix_core_tareas_corridas_tarea; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_tareas_corridas_tarea ON public.core_tareas_corridas USING btree (tarea, creada_at);


--
-- Name: ix_core_usuarios_deleted_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_usuarios_deleted_at ON public.core_usuarios USING btree (deleted_at);


--
-- Name: ix_core_usuarios_dni; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_usuarios_dni ON public.core_usuarios USING btree (dni);


--
-- Name: ix_core_usuarios_email; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_core_usuarios_email ON public.core_usuarios USING btree (email);


--
-- Name: ix_core_usuarios_magic_link_token; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_core_usuarios_magic_link_token ON public.core_usuarios USING btree (magic_link_token);


--
-- Name: ix_notificaciones_internas_usuario_bandeja_v2; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notificaciones_internas_usuario_bandeja_v2 ON public.core_notificaciones_internas USING btree (empresa_id, usuario_id, deleted_at, leida_at, created_at);


--
-- Name: ix_notificaciones_log_empleado_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notificaciones_log_empleado_id ON public.notificaciones_log USING btree (empleado_id);


--
-- Name: ix_notificaciones_log_estado; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notificaciones_log_estado ON public.notificaciones_log USING btree (estado);


--
-- Name: ix_notificaciones_log_fecha_evento; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notificaciones_log_fecha_evento ON public.notificaciones_log USING btree (fecha_evento);


--
-- Name: ix_notificaciones_log_tipo; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_notificaciones_log_tipo ON public.notificaciones_log USING btree (tipo);


--
-- Name: ix_proveedores_auditoria_entidad; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_proveedores_auditoria_entidad ON public.proveedores_auditoria USING btree (entidad, entidad_id, fecha_hora);


--
-- Name: ix_proveedores_auditoria_evaluacion; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_proveedores_auditoria_evaluacion ON public.proveedores_auditoria USING btree (evaluacion_id, fecha_hora);


--
-- Name: ix_proveedores_contactos_proveedor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_proveedores_contactos_proveedor ON public.proveedores_contactos USING btree (proveedor_id);


--
-- Name: ix_proveedores_documentos_proveedor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_proveedores_documentos_proveedor ON public.proveedores_documentos USING btree (proveedor_id);


--
-- Name: ix_proveedores_importacion_filas; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_proveedores_importacion_filas ON public.proveedores_importacion_filas USING btree (importacion_id);


--
-- Name: ix_proveedores_item_evaluador; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_proveedores_item_evaluador ON public.proveedores_evaluacion_items USING btree (evaluacion_id, evaluador_empleado_id);


--
-- Name: ix_proveedores_oficinas_proveedor; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_proveedores_oficinas_proveedor ON public.proveedores_oficinas USING btree (proveedor_id);


--
-- Name: ix_proveedores_referente; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_proveedores_referente ON public.proveedores_proveedores USING btree (referente_empleado_id);


--
-- Name: ix_starmiles_inscripciones_desafio_empleado_estado; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_starmiles_inscripciones_desafio_empleado_estado ON public.starmiles_inscripciones USING btree (empresa_id, desafio_id, empleado_id, estado);


--
-- Name: uq_core_envios_clave; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_core_envios_clave ON public.core_envios USING btree (clave) WHERE (clave IS NOT NULL);


--
-- Name: uq_herramienta_empresa_nombre; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_herramienta_empresa_nombre ON public.innovacion_herramientas USING btree (empresa_id, nombre_normalizado) WHERE (deleted_at IS NULL);


--
-- Name: uq_proveedor_empresa_nombre; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_proveedor_empresa_nombre ON public.innovacion_proveedores USING btree (empresa_id, nombre_normalizado) WHERE (deleted_at IS NULL);


--
-- Name: uq_proveedores_aviso_diario; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_proveedores_aviso_diario ON public.proveedores_avisos USING btree (evaluacion_id, motivo, canal, COALESCE(empleado_id, '00000000-0000-0000-0000-000000000000'::uuid), fecha_local) WHERE (enviado AND ((motivo)::text <> 'manual'::text));


--
-- Name: uq_proveedores_contacto_principal; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_proveedores_contacto_principal ON public.proveedores_contactos USING btree (proveedor_id) WHERE (es_principal AND (deleted_at IS NULL));


--
-- Name: uq_proveedores_empresa_nombre; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_proveedores_empresa_nombre ON public.proveedores_proveedores USING btree (empresa_id, lower(btrim((nombre)::text))) WHERE (deleted_at IS NULL);


--
-- Name: uq_proveedores_evaluacion_periodo; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_proveedores_evaluacion_periodo ON public.proveedores_evaluaciones USING btree (empresa_id, periodo) WHERE (deleted_at IS NULL);


--
-- Name: uq_proveedores_evaluacion_vigente; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_proveedores_evaluacion_vigente ON public.proveedores_evaluaciones USING btree (empresa_id) WHERE ((reemplazada_at IS NULL) AND (deleted_at IS NULL));


--
-- Name: uq_proveedores_item_evaluacion_proveedor; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_proveedores_item_evaluacion_proveedor ON public.proveedores_evaluacion_items USING btree (evaluacion_id, proveedor_id) WHERE (deleted_at IS NULL);


--
-- Name: uq_proveedores_oficina_legal; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX uq_proveedores_oficina_legal ON public.proveedores_oficinas USING btree (proveedor_id) WHERE (es_legal AND (deleted_at IS NULL));


--
-- Name: admin_categorias_cliente admin_categorias_cliente_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_categorias_cliente
    ADD CONSTRAINT admin_categorias_cliente_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: admin_cliente_categoria admin_cliente_categoria_categoria_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_cliente_categoria
    ADD CONSTRAINT admin_cliente_categoria_categoria_id_fkey FOREIGN KEY (categoria_id) REFERENCES public.admin_categorias_cliente(id);


--
-- Name: admin_cliente_categoria admin_cliente_categoria_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_cliente_categoria
    ADD CONSTRAINT admin_cliente_categoria_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.admin_clientes(id);


--
-- Name: admin_cliente_domicilios admin_cliente_domicilios_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_cliente_domicilios
    ADD CONSTRAINT admin_cliente_domicilios_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.admin_clientes(id);


--
-- Name: admin_cliente_domicilios admin_cliente_domicilios_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_cliente_domicilios
    ADD CONSTRAINT admin_cliente_domicilios_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: admin_clientes admin_clientes_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.admin_clientes
    ADD CONSTRAINT admin_clientes_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: innovacion_licencias admin_licencias_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_licencias
    ADD CONSTRAINT admin_licencias_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: innovacion_licencias admin_licencias_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_licencias
    ADD CONSTRAINT admin_licencias_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: core_auditoria_log core_auditoria_log_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_auditoria_log
    ADD CONSTRAINT core_auditoria_log_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: core_empresa_domicilios core_empresa_domicilios_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_empresa_domicilios
    ADD CONSTRAINT core_empresa_domicilios_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: core_grupo_departamento core_grupo_departamento_departamento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_grupo_departamento
    ADD CONSTRAINT core_grupo_departamento_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES public.nomina_departamentos(id);


--
-- Name: core_grupo_departamento core_grupo_departamento_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_grupo_departamento
    ADD CONSTRAINT core_grupo_departamento_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: core_grupo_departamento core_grupo_departamento_grupo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_grupo_departamento
    ADD CONSTRAINT core_grupo_departamento_grupo_id_fkey FOREIGN KEY (grupo_id) REFERENCES public.core_grupos(id);


--
-- Name: core_grupo_menu core_grupo_menu_grupo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_grupo_menu
    ADD CONSTRAINT core_grupo_menu_grupo_id_fkey FOREIGN KEY (grupo_id) REFERENCES public.core_grupos(id);


--
-- Name: core_grupo_menu core_grupo_menu_menu_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_grupo_menu
    ADD CONSTRAINT core_grupo_menu_menu_id_fkey FOREIGN KEY (menu_id) REFERENCES public.core_menus(id);


--
-- Name: core_menu_items core_menu_items_menu_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_menu_items
    ADD CONSTRAINT core_menu_items_menu_id_fkey FOREIGN KEY (menu_id) REFERENCES public.core_menus(id);


--
-- Name: core_notificaciones_internas core_notificaciones_internas_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_notificaciones_internas
    ADD CONSTRAINT core_notificaciones_internas_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: core_notificaciones_internas core_notificaciones_internas_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_notificaciones_internas
    ADD CONSTRAINT core_notificaciones_internas_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.core_usuarios(id);


--
-- Name: core_oidc_codigos core_oidc_codigos_cliente_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_oidc_codigos
    ADD CONSTRAINT core_oidc_codigos_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES public.core_oidc_clientes(id);


--
-- Name: core_oidc_codigos core_oidc_codigos_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_oidc_codigos
    ADD CONSTRAINT core_oidc_codigos_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.core_usuarios(id);


--
-- Name: core_permisos_modulo core_permisos_modulo_grupo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_permisos_modulo
    ADD CONSTRAINT core_permisos_modulo_grupo_id_fkey FOREIGN KEY (grupo_id) REFERENCES public.core_grupos(id);


--
-- Name: core_usuario_empresa core_usuario_empresa_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_usuario_empresa
    ADD CONSTRAINT core_usuario_empresa_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: core_usuario_empresa core_usuario_empresa_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_usuario_empresa
    ADD CONSTRAINT core_usuario_empresa_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.core_usuarios(id);


--
-- Name: core_usuario_grupo core_usuario_grupo_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_usuario_grupo
    ADD CONSTRAINT core_usuario_grupo_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: core_usuario_grupo core_usuario_grupo_grupo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_usuario_grupo
    ADD CONSTRAINT core_usuario_grupo_grupo_id_fkey FOREIGN KEY (grupo_id) REFERENCES public.core_grupos(id);


--
-- Name: core_usuario_grupo core_usuario_grupo_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.core_usuario_grupo
    ADD CONSTRAINT core_usuario_grupo_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.core_usuarios(id);


--
-- Name: hrbp_entregas hrbp_entregas_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hrbp_entregas
    ADD CONSTRAINT hrbp_entregas_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: hrbp_entregas hrbp_entregas_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hrbp_entregas
    ADD CONSTRAINT hrbp_entregas_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: hrbp_entregas hrbp_entregas_hrbp_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hrbp_entregas
    ADD CONSTRAINT hrbp_entregas_hrbp_usuario_id_fkey FOREIGN KEY (hrbp_usuario_id) REFERENCES public.core_usuarios(id);


--
-- Name: hrbp_entregas hrbp_entregas_item_tipo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hrbp_entregas
    ADD CONSTRAINT hrbp_entregas_item_tipo_id_fkey FOREIGN KEY (item_tipo_id) REFERENCES public.hrbp_item_tipos(id);


--
-- Name: hrbp_item_tipos hrbp_item_tipos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hrbp_item_tipos
    ADD CONSTRAINT hrbp_item_tipos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: innovacion_certificaciones innovacion_certificaciones_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_certificaciones
    ADD CONSTRAINT innovacion_certificaciones_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: innovacion_certificaciones innovacion_certificaciones_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_certificaciones
    ADD CONSTRAINT innovacion_certificaciones_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: innovacion_evento_asistencia innovacion_evento_asistencia_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_evento_asistencia
    ADD CONSTRAINT innovacion_evento_asistencia_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: innovacion_evento_asistencia innovacion_evento_asistencia_evento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_evento_asistencia
    ADD CONSTRAINT innovacion_evento_asistencia_evento_id_fkey FOREIGN KEY (evento_id) REFERENCES public.innovacion_eventos(id);


--
-- Name: innovacion_eventos innovacion_eventos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_eventos
    ADD CONSTRAINT innovacion_eventos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: innovacion_herramientas innovacion_herramientas_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_herramientas
    ADD CONSTRAINT innovacion_herramientas_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: innovacion_herramientas innovacion_herramientas_proveedor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_herramientas
    ADD CONSTRAINT innovacion_herramientas_proveedor_id_fkey FOREIGN KEY (proveedor_id) REFERENCES public.innovacion_proveedores(id);


--
-- Name: innovacion_licencias innovacion_licencias_herramienta_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_licencias
    ADD CONSTRAINT innovacion_licencias_herramienta_id_fkey FOREIGN KEY (herramienta_id) REFERENCES public.innovacion_herramientas(id);


--
-- Name: innovacion_proveedores innovacion_proveedores_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.innovacion_proveedores
    ADD CONSTRAINT innovacion_proveedores_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: nomina_carreras nomina_carreras_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_carreras
    ADD CONSTRAINT nomina_carreras_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: nomina_categorias nomina_categorias_departamento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_categorias
    ADD CONSTRAINT nomina_categorias_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES public.nomina_departamentos(id);


--
-- Name: nomina_categorias nomina_categorias_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_categorias
    ADD CONSTRAINT nomina_categorias_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: nomina_departamentos nomina_departamentos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_departamentos
    ADD CONSTRAINT nomina_departamentos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: nomina_departamentos nomina_departamentos_manager_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_departamentos
    ADD CONSTRAINT nomina_departamentos_manager_id_fkey FOREIGN KEY (manager_id) REFERENCES public.nomina_empleados(id);


--
-- Name: nomina_empleados nomina_empleados_carrera_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_empleados
    ADD CONSTRAINT nomina_empleados_carrera_id_fkey FOREIGN KEY (carrera_id) REFERENCES public.nomina_carreras(id);


--
-- Name: nomina_empleados nomina_empleados_departamento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_empleados
    ADD CONSTRAINT nomina_empleados_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES public.nomina_departamentos(id);


--
-- Name: nomina_empleados nomina_empleados_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_empleados
    ADD CONSTRAINT nomina_empleados_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: nomina_empleados nomina_empleados_hrbp_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_empleados
    ADD CONSTRAINT nomina_empleados_hrbp_id_fkey FOREIGN KEY (hrbp_id) REFERENCES public.nomina_empleados(id);


--
-- Name: nomina_empleados nomina_empleados_perfil_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_empleados
    ADD CONSTRAINT nomina_empleados_perfil_id_fkey FOREIGN KEY (perfil_id) REFERENCES public.nomina_perfiles(id);


--
-- Name: nomina_perfiles nomina_perfiles_categoria_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_perfiles
    ADD CONSTRAINT nomina_perfiles_categoria_id_fkey FOREIGN KEY (categoria_id) REFERENCES public.nomina_categorias(id);


--
-- Name: nomina_perfiles nomina_perfiles_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.nomina_perfiles
    ADD CONSTRAINT nomina_perfiles_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: operaciones_equipo_integrantes operaciones_equipo_integrantes_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operaciones_equipo_integrantes
    ADD CONSTRAINT operaciones_equipo_integrantes_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: operaciones_equipo_integrantes operaciones_equipo_integrantes_equipo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operaciones_equipo_integrantes
    ADD CONSTRAINT operaciones_equipo_integrantes_equipo_id_fkey FOREIGN KEY (equipo_id) REFERENCES public.operaciones_equipos(id);


--
-- Name: operaciones_equipos operaciones_equipos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operaciones_equipos
    ADD CONSTRAINT operaciones_equipos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: operaciones_equipos operaciones_equipos_lider_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.operaciones_equipos
    ADD CONSTRAINT operaciones_equipos_lider_id_fkey FOREIGN KEY (lider_id) REFERENCES public.nomina_empleados(id);


--
-- Name: proveedores_auditoria proveedores_auditoria_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_auditoria
    ADD CONSTRAINT proveedores_auditoria_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: proveedores_auditoria proveedores_auditoria_evaluacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_auditoria
    ADD CONSTRAINT proveedores_auditoria_evaluacion_id_fkey FOREIGN KEY (evaluacion_id) REFERENCES public.proveedores_evaluaciones(id);


--
-- Name: proveedores_auditoria proveedores_auditoria_usuario_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_auditoria
    ADD CONSTRAINT proveedores_auditoria_usuario_id_fkey FOREIGN KEY (usuario_id) REFERENCES public.core_usuarios(id);


--
-- Name: proveedores_avisos proveedores_avisos_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_avisos
    ADD CONSTRAINT proveedores_avisos_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: proveedores_avisos proveedores_avisos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_avisos
    ADD CONSTRAINT proveedores_avisos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: proveedores_avisos proveedores_avisos_enviado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_avisos
    ADD CONSTRAINT proveedores_avisos_enviado_por_fkey FOREIGN KEY (enviado_por) REFERENCES public.core_usuarios(id);


--
-- Name: proveedores_avisos proveedores_avisos_evaluacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_avisos
    ADD CONSTRAINT proveedores_avisos_evaluacion_id_fkey FOREIGN KEY (evaluacion_id) REFERENCES public.proveedores_evaluaciones(id);


--
-- Name: proveedores_configuracion proveedores_configuracion_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_configuracion
    ADD CONSTRAINT proveedores_configuracion_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: proveedores_contactos proveedores_contactos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_contactos
    ADD CONSTRAINT proveedores_contactos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: proveedores_contactos proveedores_contactos_oficina_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_contactos
    ADD CONSTRAINT proveedores_contactos_oficina_id_fkey FOREIGN KEY (oficina_id) REFERENCES public.proveedores_oficinas(id);


--
-- Name: proveedores_contactos proveedores_contactos_proveedor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_contactos
    ADD CONSTRAINT proveedores_contactos_proveedor_id_fkey FOREIGN KEY (proveedor_id) REFERENCES public.proveedores_proveedores(id);


--
-- Name: proveedores_documentos proveedores_documentos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_documentos
    ADD CONSTRAINT proveedores_documentos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: proveedores_documentos proveedores_documentos_proveedor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_documentos
    ADD CONSTRAINT proveedores_documentos_proveedor_id_fkey FOREIGN KEY (proveedor_id) REFERENCES public.proveedores_proveedores(id);


--
-- Name: proveedores_evaluacion_items proveedores_evaluacion_items_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_evaluacion_items
    ADD CONSTRAINT proveedores_evaluacion_items_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: proveedores_evaluacion_items proveedores_evaluacion_items_evaluacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_evaluacion_items
    ADD CONSTRAINT proveedores_evaluacion_items_evaluacion_id_fkey FOREIGN KEY (evaluacion_id) REFERENCES public.proveedores_evaluaciones(id);


--
-- Name: proveedores_evaluacion_items proveedores_evaluacion_items_evaluado_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_evaluacion_items
    ADD CONSTRAINT proveedores_evaluacion_items_evaluado_por_fkey FOREIGN KEY (evaluado_por) REFERENCES public.core_usuarios(id);


--
-- Name: proveedores_evaluacion_items proveedores_evaluacion_items_evaluador_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_evaluacion_items
    ADD CONSTRAINT proveedores_evaluacion_items_evaluador_empleado_id_fkey FOREIGN KEY (evaluador_empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: proveedores_evaluacion_items proveedores_evaluacion_items_proveedor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_evaluacion_items
    ADD CONSTRAINT proveedores_evaluacion_items_proveedor_id_fkey FOREIGN KEY (proveedor_id) REFERENCES public.proveedores_proveedores(id);


--
-- Name: proveedores_evaluaciones proveedores_evaluaciones_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_evaluaciones
    ADD CONSTRAINT proveedores_evaluaciones_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: proveedores_importacion_filas proveedores_importacion_filas_importacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_importacion_filas
    ADD CONSTRAINT proveedores_importacion_filas_importacion_id_fkey FOREIGN KEY (importacion_id) REFERENCES public.proveedores_importaciones(id) ON DELETE CASCADE;


--
-- Name: proveedores_importaciones proveedores_importaciones_creada_por_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_importaciones
    ADD CONSTRAINT proveedores_importaciones_creada_por_fkey FOREIGN KEY (creada_por) REFERENCES public.core_usuarios(id);


--
-- Name: proveedores_importaciones proveedores_importaciones_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_importaciones
    ADD CONSTRAINT proveedores_importaciones_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: proveedores_importaciones proveedores_importaciones_evaluacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_importaciones
    ADD CONSTRAINT proveedores_importaciones_evaluacion_id_fkey FOREIGN KEY (evaluacion_id) REFERENCES public.proveedores_evaluaciones(id);


--
-- Name: proveedores_oficinas proveedores_oficinas_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_oficinas
    ADD CONSTRAINT proveedores_oficinas_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: proveedores_oficinas proveedores_oficinas_proveedor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_oficinas
    ADD CONSTRAINT proveedores_oficinas_proveedor_id_fkey FOREIGN KEY (proveedor_id) REFERENCES public.proveedores_proveedores(id);


--
-- Name: proveedores_proveedores proveedores_proveedores_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_proveedores
    ADD CONSTRAINT proveedores_proveedores_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: proveedores_proveedores proveedores_proveedores_referente_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proveedores_proveedores
    ADD CONSTRAINT proveedores_proveedores_referente_empleado_id_fkey FOREIGN KEY (referente_empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: recibos_logs recibos_logs_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recibos_logs
    ADD CONSTRAINT recibos_logs_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: recibos_logs recibos_logs_recibo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recibos_logs
    ADD CONSTRAINT recibos_logs_recibo_id_fkey FOREIGN KEY (recibo_id) REFERENCES public.recibos_recibos(id);


--
-- Name: recibos_lotes recibos_lotes_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recibos_lotes
    ADD CONSTRAINT recibos_lotes_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: recibos_recibos recibos_recibos_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recibos_recibos
    ADD CONSTRAINT recibos_recibos_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: recibos_recibos recibos_recibos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recibos_recibos
    ADD CONSTRAINT recibos_recibos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: recibos_recibos recibos_recibos_lote_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.recibos_recibos
    ADD CONSTRAINT recibos_recibos_lote_id_fkey FOREIGN KEY (lote_id) REFERENCES public.recibos_lotes(id);


--
-- Name: soporte_activos soporte_activos_asignado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos
    ADD CONSTRAINT soporte_activos_asignado_id_fkey FOREIGN KEY (asignado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_activos soporte_activos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos
    ADD CONSTRAINT soporte_activos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_activos_especificaciones soporte_activos_especificaciones_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos_especificaciones
    ADD CONSTRAINT soporte_activos_especificaciones_id_fkey FOREIGN KEY (id) REFERENCES public.soporte_activos(id) ON DELETE CASCADE;


--
-- Name: soporte_activos soporte_activos_marca_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos
    ADD CONSTRAINT soporte_activos_marca_id_fkey FOREIGN KEY (marca_id) REFERENCES public.soporte_activos_marcas(id);


--
-- Name: soporte_activos_marcas soporte_activos_marcas_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos_marcas
    ADD CONSTRAINT soporte_activos_marcas_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_activos soporte_activos_matriz_estado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos
    ADD CONSTRAINT soporte_activos_matriz_estado_id_fkey FOREIGN KEY (matriz_estado_id) REFERENCES public.soporte_matriz_estado(id);


--
-- Name: soporte_activos soporte_activos_tipo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos
    ADD CONSTRAINT soporte_activos_tipo_id_fkey FOREIGN KEY (tipo_id) REFERENCES public.soporte_activos_tipos(id);


--
-- Name: soporte_activos_tipos soporte_activos_tipos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_activos_tipos
    ADD CONSTRAINT soporte_activos_tipos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_categorias soporte_categorias_departamento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_categorias
    ADD CONSTRAINT soporte_categorias_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES public.nomina_departamentos(id);


--
-- Name: soporte_categorias soporte_categorias_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_categorias
    ADD CONSTRAINT soporte_categorias_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_evidencias soporte_evidencias_activo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_evidencias
    ADD CONSTRAINT soporte_evidencias_activo_id_fkey FOREIGN KEY (activo_id) REFERENCES public.soporte_activos(id);


--
-- Name: soporte_evidencias soporte_evidencias_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_evidencias
    ADD CONSTRAINT soporte_evidencias_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_evidencias soporte_evidencias_historial_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_evidencias
    ADD CONSTRAINT soporte_evidencias_historial_id_fkey FOREIGN KEY (historial_id) REFERENCES public.soporte_historial_activo(id);


--
-- Name: soporte_evidencias soporte_evidencias_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_evidencias
    ADD CONSTRAINT soporte_evidencias_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.soporte_tickets(id);


--
-- Name: soporte_historial_activo soporte_historial_activo_activo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_historial_activo
    ADD CONSTRAINT soporte_historial_activo_activo_id_fkey FOREIGN KEY (activo_id) REFERENCES public.soporte_activos(id);


--
-- Name: soporte_historial_activo soporte_historial_activo_colaborador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_historial_activo
    ADD CONSTRAINT soporte_historial_activo_colaborador_id_fkey FOREIGN KEY (colaborador_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_historial_activo soporte_historial_activo_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_historial_activo
    ADD CONSTRAINT soporte_historial_activo_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_historial_activo soporte_historial_activo_matriz_estado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_historial_activo
    ADD CONSTRAINT soporte_historial_activo_matriz_estado_id_fkey FOREIGN KEY (matriz_estado_id) REFERENCES public.soporte_matriz_estado(id);


--
-- Name: soporte_historial_activo soporte_historial_activo_pedido_compra_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_historial_activo
    ADD CONSTRAINT soporte_historial_activo_pedido_compra_id_fkey FOREIGN KEY (pedido_compra_id) REFERENCES public.soporte_pedidos_compra(id);


--
-- Name: soporte_historial_activo soporte_historial_activo_responsable_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_historial_activo
    ADD CONSTRAINT soporte_historial_activo_responsable_id_fkey FOREIGN KEY (responsable_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_insumos soporte_insumos_categoria_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_insumos
    ADD CONSTRAINT soporte_insumos_categoria_id_fkey FOREIGN KEY (categoria_id) REFERENCES public.soporte_categorias(id);


--
-- Name: soporte_insumos soporte_insumos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_insumos
    ADD CONSTRAINT soporte_insumos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_mantenimiento_evento soporte_mantenimiento_evento_activo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_mantenimiento_evento
    ADD CONSTRAINT soporte_mantenimiento_evento_activo_id_fkey FOREIGN KEY (activo_id) REFERENCES public.soporte_activos(id);


--
-- Name: soporte_mantenimiento_evento soporte_mantenimiento_evento_asignado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_mantenimiento_evento
    ADD CONSTRAINT soporte_mantenimiento_evento_asignado_id_fkey FOREIGN KEY (asignado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_mantenimiento_evento soporte_mantenimiento_evento_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_mantenimiento_evento
    ADD CONSTRAINT soporte_mantenimiento_evento_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_matriz_estado soporte_matriz_estado_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_matriz_estado
    ADD CONSTRAINT soporte_matriz_estado_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_movimientos_insumos soporte_movimientos_insumos_activo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_movimientos_insumos
    ADD CONSTRAINT soporte_movimientos_insumos_activo_id_fkey FOREIGN KEY (activo_id) REFERENCES public.soporte_activos(id);


--
-- Name: soporte_movimientos_insumos soporte_movimientos_insumos_empleado_asignador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_movimientos_insumos
    ADD CONSTRAINT soporte_movimientos_insumos_empleado_asignador_id_fkey FOREIGN KEY (empleado_asignador_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_movimientos_insumos soporte_movimientos_insumos_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_movimientos_insumos
    ADD CONSTRAINT soporte_movimientos_insumos_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_movimientos_insumos soporte_movimientos_insumos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_movimientos_insumos
    ADD CONSTRAINT soporte_movimientos_insumos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_movimientos_insumos soporte_movimientos_insumos_insumo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_movimientos_insumos
    ADD CONSTRAINT soporte_movimientos_insumos_insumo_id_fkey FOREIGN KEY (insumo_id) REFERENCES public.soporte_insumos(id);


--
-- Name: soporte_movimientos_insumos soporte_movimientos_insumos_pedido_compra_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_movimientos_insumos
    ADD CONSTRAINT soporte_movimientos_insumos_pedido_compra_id_fkey FOREIGN KEY (pedido_compra_id) REFERENCES public.soporte_pedidos_compra(id);


--
-- Name: soporte_pedidos_aprobaciones soporte_pedidos_aprobaciones_aprobador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_aprobaciones
    ADD CONSTRAINT soporte_pedidos_aprobaciones_aprobador_id_fkey FOREIGN KEY (aprobador_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_pedidos_aprobaciones soporte_pedidos_aprobaciones_departamento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_aprobaciones
    ADD CONSTRAINT soporte_pedidos_aprobaciones_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES public.nomina_departamentos(id);


--
-- Name: soporte_pedidos_aprobaciones soporte_pedidos_aprobaciones_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_aprobaciones
    ADD CONSTRAINT soporte_pedidos_aprobaciones_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_pedidos_aprobaciones soporte_pedidos_aprobaciones_pedido_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_aprobaciones
    ADD CONSTRAINT soporte_pedidos_aprobaciones_pedido_id_fkey FOREIGN KEY (pedido_id) REFERENCES public.soporte_pedidos_compra(id);


--
-- Name: soporte_pedidos_compra soporte_pedidos_compra_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_compra
    ADD CONSTRAINT soporte_pedidos_compra_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_pedidos_compra soporte_pedidos_compra_estado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_compra
    ADD CONSTRAINT soporte_pedidos_compra_estado_id_fkey FOREIGN KEY (estado_id) REFERENCES public.soporte_pedidos_estados(id);


--
-- Name: soporte_pedidos_compra soporte_pedidos_compra_insumo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_compra
    ADD CONSTRAINT soporte_pedidos_compra_insumo_id_fkey FOREIGN KEY (insumo_id) REFERENCES public.soporte_insumos(id);


--
-- Name: soporte_pedidos_compra soporte_pedidos_compra_solicitante_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_compra
    ADD CONSTRAINT soporte_pedidos_compra_solicitante_id_fkey FOREIGN KEY (solicitante_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_pedidos_compra soporte_pedidos_compra_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_compra
    ADD CONSTRAINT soporte_pedidos_compra_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.soporte_tickets(id);


--
-- Name: soporte_pedidos_presupuestos soporte_pedidos_presupuestos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_presupuestos
    ADD CONSTRAINT soporte_pedidos_presupuestos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_pedidos_presupuestos soporte_pedidos_presupuestos_pedido_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_pedidos_presupuestos
    ADD CONSTRAINT soporte_pedidos_presupuestos_pedido_id_fkey FOREIGN KEY (pedido_id) REFERENCES public.soporte_pedidos_compra(id);


--
-- Name: soporte_sistemas_disponibles soporte_sistemas_disponibles_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_sistemas_disponibles
    ADD CONSTRAINT soporte_sistemas_disponibles_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_subcategorias soporte_subcategorias_categoria_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_subcategorias
    ADD CONSTRAINT soporte_subcategorias_categoria_id_fkey FOREIGN KEY (categoria_id) REFERENCES public.soporte_categorias(id);


--
-- Name: soporte_subcategorias soporte_subcategorias_departamento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_subcategorias
    ADD CONSTRAINT soporte_subcategorias_departamento_id_fkey FOREIGN KEY (departamento_id) REFERENCES public.nomina_departamentos(id);


--
-- Name: soporte_subcategorias soporte_subcategorias_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_subcategorias
    ADD CONSTRAINT soporte_subcategorias_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_ticket_checklist_items soporte_ticket_checklist_items_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_ticket_checklist_items
    ADD CONSTRAINT soporte_ticket_checklist_items_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_ticket_checklist_items soporte_ticket_checklist_items_sistema_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_ticket_checklist_items
    ADD CONSTRAINT soporte_ticket_checklist_items_sistema_id_fkey FOREIGN KEY (sistema_id) REFERENCES public.soporte_sistemas_disponibles(id);


--
-- Name: soporte_ticket_checklist_items soporte_ticket_checklist_items_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_ticket_checklist_items
    ADD CONSTRAINT soporte_ticket_checklist_items_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.soporte_tickets(id) ON DELETE CASCADE;


--
-- Name: soporte_tickets_alta_baja soporte_tickets_alta_baja_activo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_alta_baja
    ADD CONSTRAINT soporte_tickets_alta_baja_activo_id_fkey FOREIGN KEY (activo_id) REFERENCES public.soporte_activos(id);


--
-- Name: soporte_tickets_alta_baja soporte_tickets_alta_baja_colaborador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_alta_baja
    ADD CONSTRAINT soporte_tickets_alta_baja_colaborador_id_fkey FOREIGN KEY (colaborador_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_tickets_alta_baja soporte_tickets_alta_baja_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_alta_baja
    ADD CONSTRAINT soporte_tickets_alta_baja_id_fkey FOREIGN KEY (id) REFERENCES public.soporte_tickets(id) ON DELETE CASCADE;


--
-- Name: soporte_tickets_alta_baja soporte_tickets_alta_baja_matriz_estado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_alta_baja
    ADD CONSTRAINT soporte_tickets_alta_baja_matriz_estado_id_fkey FOREIGN KEY (matriz_estado_id) REFERENCES public.soporte_matriz_estado(id);


--
-- Name: soporte_tickets soporte_tickets_asignado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets
    ADD CONSTRAINT soporte_tickets_asignado_id_fkey FOREIGN KEY (asignado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_tickets soporte_tickets_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets
    ADD CONSTRAINT soporte_tickets_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_tickets soporte_tickets_estado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets
    ADD CONSTRAINT soporte_tickets_estado_id_fkey FOREIGN KEY (estado_id) REFERENCES public.soporte_tickets_estados(id);


--
-- Name: soporte_tickets_insumos soporte_tickets_insumos_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_insumos
    ADD CONSTRAINT soporte_tickets_insumos_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: soporte_tickets_insumos soporte_tickets_insumos_insumo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_insumos
    ADD CONSTRAINT soporte_tickets_insumos_insumo_id_fkey FOREIGN KEY (insumo_id) REFERENCES public.soporte_insumos(id);


--
-- Name: soporte_tickets_insumos soporte_tickets_insumos_movimiento_insumo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_insumos
    ADD CONSTRAINT soporte_tickets_insumos_movimiento_insumo_id_fkey FOREIGN KEY (movimiento_insumo_id) REFERENCES public.soporte_movimientos_insumos(id);


--
-- Name: soporte_tickets_insumos soporte_tickets_insumos_pedido_compra_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_insumos
    ADD CONSTRAINT soporte_tickets_insumos_pedido_compra_id_fkey FOREIGN KEY (pedido_compra_id) REFERENCES public.soporte_pedidos_compra(id);


--
-- Name: soporte_tickets_insumos soporte_tickets_insumos_ticket_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_insumos
    ADD CONSTRAINT soporte_tickets_insumos_ticket_id_fkey FOREIGN KEY (ticket_id) REFERENCES public.soporte_tickets(id) ON DELETE CASCADE;


--
-- Name: soporte_tickets_mantenimiento soporte_tickets_mantenimiento_activo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_mantenimiento
    ADD CONSTRAINT soporte_tickets_mantenimiento_activo_id_fkey FOREIGN KEY (activo_id) REFERENCES public.soporte_activos(id);


--
-- Name: soporte_tickets_mantenimiento soporte_tickets_mantenimiento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_mantenimiento
    ADD CONSTRAINT soporte_tickets_mantenimiento_id_fkey FOREIGN KEY (id) REFERENCES public.soporte_tickets(id) ON DELETE CASCADE;


--
-- Name: soporte_tickets_mantenimiento soporte_tickets_mantenimiento_mantenimiento_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_mantenimiento
    ADD CONSTRAINT soporte_tickets_mantenimiento_mantenimiento_id_fkey FOREIGN KEY (mantenimiento_id) REFERENCES public.soporte_mantenimiento_evento(id);


--
-- Name: soporte_tickets_reparacion soporte_tickets_reparacion_activo_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_reparacion
    ADD CONSTRAINT soporte_tickets_reparacion_activo_id_fkey FOREIGN KEY (activo_id) REFERENCES public.soporte_activos(id);


--
-- Name: soporte_tickets_reparacion soporte_tickets_reparacion_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_reparacion
    ADD CONSTRAINT soporte_tickets_reparacion_id_fkey FOREIGN KEY (id) REFERENCES public.soporte_tickets(id) ON DELETE CASCADE;


--
-- Name: soporte_tickets_reparacion soporte_tickets_reparacion_matriz_entrada_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_reparacion
    ADD CONSTRAINT soporte_tickets_reparacion_matriz_entrada_id_fkey FOREIGN KEY (matriz_entrada_id) REFERENCES public.soporte_matriz_estado(id);


--
-- Name: soporte_tickets_reparacion soporte_tickets_reparacion_matriz_salida_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets_reparacion
    ADD CONSTRAINT soporte_tickets_reparacion_matriz_salida_id_fkey FOREIGN KEY (matriz_salida_id) REFERENCES public.soporte_matriz_estado(id);


--
-- Name: soporte_tickets soporte_tickets_solicitante_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets
    ADD CONSTRAINT soporte_tickets_solicitante_id_fkey FOREIGN KEY (solicitante_id) REFERENCES public.nomina_empleados(id);


--
-- Name: soporte_tickets soporte_tickets_subcategoria_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.soporte_tickets
    ADD CONSTRAINT soporte_tickets_subcategoria_id_fkey FOREIGN KEY (subcategoria_id) REFERENCES public.soporte_subcategorias(id);


--
-- Name: starmiles_canjes starmiles_canjes_aprobador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_canjes
    ADD CONSTRAINT starmiles_canjes_aprobador_id_fkey FOREIGN KEY (aprobador_id) REFERENCES public.nomina_empleados(id);


--
-- Name: starmiles_canjes starmiles_canjes_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_canjes
    ADD CONSTRAINT starmiles_canjes_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: starmiles_canjes starmiles_canjes_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_canjes
    ADD CONSTRAINT starmiles_canjes_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: starmiles_canjes starmiles_canjes_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_canjes
    ADD CONSTRAINT starmiles_canjes_item_id_fkey FOREIGN KEY (item_id) REFERENCES public.starmiles_items_canje(id);


--
-- Name: starmiles_categorias starmiles_categorias_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_categorias
    ADD CONSTRAINT starmiles_categorias_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: starmiles_contenido_cms starmiles_contenido_cms_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_contenido_cms
    ADD CONSTRAINT starmiles_contenido_cms_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: starmiles_contenido_cms starmiles_contenido_cms_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_contenido_cms
    ADD CONSTRAINT starmiles_contenido_cms_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: starmiles_desafios starmiles_desafios_categoria_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_desafios
    ADD CONSTRAINT starmiles_desafios_categoria_id_fkey FOREIGN KEY (categoria_id) REFERENCES public.starmiles_categorias(id);


--
-- Name: starmiles_desafios starmiles_desafios_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_desafios
    ADD CONSTRAINT starmiles_desafios_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: starmiles_empleados starmiles_empleados_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_empleados
    ADD CONSTRAINT starmiles_empleados_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: starmiles_empleados starmiles_empleados_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_empleados
    ADD CONSTRAINT starmiles_empleados_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: starmiles_inscripciones starmiles_inscripciones_aprobador_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_inscripciones
    ADD CONSTRAINT starmiles_inscripciones_aprobador_id_fkey FOREIGN KEY (aprobador_id) REFERENCES public.nomina_empleados(id);


--
-- Name: starmiles_inscripciones starmiles_inscripciones_desafio_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_inscripciones
    ADD CONSTRAINT starmiles_inscripciones_desafio_id_fkey FOREIGN KEY (desafio_id) REFERENCES public.starmiles_desafios(id);


--
-- Name: starmiles_inscripciones starmiles_inscripciones_empleado_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_inscripciones
    ADD CONSTRAINT starmiles_inscripciones_empleado_id_fkey FOREIGN KEY (empleado_id) REFERENCES public.nomina_empleados(id);


--
-- Name: starmiles_inscripciones starmiles_inscripciones_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_inscripciones
    ADD CONSTRAINT starmiles_inscripciones_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- Name: starmiles_items_canje starmiles_items_canje_empresa_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.starmiles_items_canje
    ADD CONSTRAINT starmiles_items_canje_empresa_id_fkey FOREIGN KEY (empresa_id) REFERENCES public.core_empresas(id);


--
-- PostgreSQL database dump complete
--

\unrestrict on0jbQJPv6XI2q9Wd1mV4vpeqblX7BHvCwjOZwSLdtFgW4DcJ1T7zFPdRHps5Jq

