"""Dicsys Core como proveedor OpenID Connect (F21): razorback y otras apps propias entran con la identidad de Core.

Ver docs/OIDC.md. El frontend publica los endpoints en core.dicsys.ai y le pasa cada pedido a la API interna de este
módulo (/api/v1/oidc/*).
"""
