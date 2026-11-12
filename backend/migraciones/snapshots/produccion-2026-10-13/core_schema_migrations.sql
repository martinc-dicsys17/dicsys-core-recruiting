--
-- PostgreSQL database dump
--

\restrict uBlDM1B3yTYI03ILS3TVqoMoXBc3V6AYHXsLbykeFymv5zVCH5kZDycIssFeXZs

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
-- Data for Name: core_schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.core_schema_migrations (id, applied_at) FROM stdin;
starmiles_dic_144_inscripcion_unica_v1	2026-07-17 12:32:08.856348
innovacion_licencias_modelo_final_v1	2026-09-07 16:06:48.014403
recibos_duplicado_opcional_v1	2026-09-07 16:06:48.892791
proveedores_acuerdo_si_no_v1	2026-10-08 00:05:36.211081
proveedores_importacion_rechazos_v1	2026-10-08 00:05:36.211081
proveedores_sin_checklist_v1	2026-10-08 00:05:36.211081
proveedores_autogeneracion_v1	2026-10-08 00:05:36.211081
proveedores_auditoria_documentos_v1	2026-10-09 16:21:55.049774
usuarios_email_secundario_v1	2026-10-12 18:50:52.272446
\.


--
-- PostgreSQL database dump complete
--

\unrestrict uBlDM1B3yTYI03ILS3TVqoMoXBc3V6AYHXsLbykeFymv5zVCH5kZDycIssFeXZs

