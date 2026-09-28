# Flujo Bitrix24 → Odoo → Bitrix24

La configuración, los mapeos y los negocios del conector son administrados por usuarios del grupo **Administración/Ajustes** (`base.group_system`). Los usuarios internos sin ese grupo no pueden leer la URL del webhook ni modificar negocios sincronizados. Para aplicar este cambio de permisos en una base ya instalada, **actualice el módulo**; desplegar archivos sin actualizarlo deja los accesos anteriores en la base de datos.

1. Despliegue el código y **actualice el módulo `bitrix24_connector`** en la base de datos. Reiniciar Odoo no crea las nuevas columnas y tablas.
2. En **Bitrix24 → Configuración**, pulse **Preparar campos de obra en Bitrix24** con un administrador. El webhook entrante usado por Odoo necesita permiso de CRM. Se crean nueve campos del negocio: código, fase, avance, fin previsto, próximo hito, fecha del hito, días de atraso, última actualización y último aviso al cliente. Puede usar campos existentes con esos tipos si introduce sus códigos `UF_CRM_...` manualmente.
3. Asocie los vendedores de Bitrix24 a los responsables de Odoo en la pestaña **Responsables**. El responsable general configurado es el respaldo.
4. Pulse **Sincronizar ahora**. Un negocio ganado crea una obra una sola vez. Odoo devuelve el avance y los hitos al mismo negocio. Los datos comerciales del negocio siguen viniendo de Bitrix24.

## Eventos inmediatos del negocio

En Bitrix24, cree un **webhook saliente** con eventos `OnCrmDealAdd` y `OnCrmDealUpdate` hacia `https://SU-DOMINIO/bitrix24/events/deal`. Copie su **Application Token** y el `member_id` del portal a la pestaña **Eventos Bitrix24** de Odoo. La URL debe ser HTTPS y pública. El endpoint valida ambos valores, consulta el negocio actualizado con `crm.deal.get` y trae su empresa o contacto si faltan en Odoo. Los eventos generados por nuestras actualizaciones no producen un ciclo de escritura porque el negocio solo se modifica en Odoo cuando cambia alguno de sus datos comerciales.

El evento acelera la recepción; la sincronización periódica sigue siendo el respaldo si Bitrix24 o la red no entrega el webhook. Un fallo del endpoint responde HTTP 503 y queda en el log de Odoo. Nunca ponga el token del webhook entrante de Odoo en la URL del evento saliente.

## Avance y avisos

El próximo hito es la actividad marcada como **Hito** aún incompleta con la fecha de fin más próxima. Los días de atraso son el máximo atraso de las actividades del cronograma. Un cambio de fase o una valorización aprobada crea un comentario en la línea de tiempo del negocio. Cada comentario lleva una marca única; antes de reintentar se busca esa marca en Bitrix24 para evitar duplicados si se perdió la respuesta anterior.

En **Avisos de avance al cliente**, seleccione un solo canal:

- **Correo desde Odoo** (predeterminado): use el botón de informe al cliente en la obra. Al generar el correo con la plantilla del informe, se registra la fecha en **Último aviso al cliente**. El campo disparador de actualización no se envía a Bitrix24.
- **Automatización en Bitrix24**: Odoo actualiza `UF_CRM_EIGR_ACTUALIZACION` al cambiar fase, avance, fin previsto, cronograma o aprobar una valorización. Configure en Bitrix24 una automatización del negocio que envíe el correo al cliente cuando cambie ese campo. El botón de envío desde Odoo queda bloqueado para obras vinculadas, evitando dos correos por el mismo avance. Revise que el negocio tenga un contacto o empresa con correo válido y que la automatización de Bitrix24 esté activa en la etapa apropiada.

El botón **Registrar aviso al cliente** de la obra permite anotar avisos hechos por otro canal. El campo `UF_CRM_EIGR_AVISO_CLIENTE` refleja la fecha registrada; no confirma por sí mismo que un correo de Bitrix24 haya sido entregado.

## Sincronización y reintentos

La primera consulta de contactos, empresas y negocios es completa. Las siguientes usan `DATE_MODIFY` con dos minutos de solapamiento; los cursores aparecen en **Sincronización incremental**. Los envíos y fallos aparecen en **Bitrix24 → Historial**. Los fallos se reintentan con espera creciente. Contactos, empresas y negocios creados en Odoo llevan un identificador de origen para recuperar el mismo registro al reintentar una creación.
