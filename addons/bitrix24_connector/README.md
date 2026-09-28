# Flujo Bitrix24 → Odoo → Bitrix24

1. Actualice el módulo `bitrix24_connector` en la base de datos de Odoo después de desplegar esta versión. El cambio añade campos y modelos; reiniciar Odoo no actualiza el esquema.
2. En **Bitrix24 → Configuración**, abra la configuración activa y pulse **Preparar campos de obra en Bitrix24** con un usuario administrador. El webhook debe tener permisos de CRM para crear campos de negocio. También puede introducir manualmente los códigos `UF_CRM_...` de cuatro campos existentes: código, estado, avance físico (número) y fin previsto (fecha).
3. En la pestaña **Responsables**, asocie cada ID de vendedor de Bitrix24 con el usuario de Odoo que recibirá sus obras. El responsable general configurado sirve de respaldo.
4. Pulse **Sincronizar ahora**. Los negocios ganados crean una obra una sola vez. Odoo devuelve al mismo negocio el código, estado, avance físico y fin previsto de la obra. Los cambios comerciales del negocio siguen viniendo de Bitrix24.

La primera consulta de contactos, empresas y negocios es completa. Las siguientes usan `DATE_MODIFY` con dos minutos de solapamiento; los cursores se muestran en la pestaña **Sincronización incremental**. Las operaciones enviadas y los fallos aparecen en **Bitrix24 → Historial**. Cada fallo tiene un próximo reintento con espera creciente; la tarea automática vuelve a intentar los vencidos aunque todavía no se cumpla el intervalo normal de sincronización.

Los nuevos contactos, empresas y negocios enviados desde Odoo llevan un identificador de origen. Antes de reintentar una creación, el conector busca ese identificador en Bitrix24 para recuperar el registro si la primera respuesta se perdió.
