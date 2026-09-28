# EIGR Gestión de Obras

Módulo academico para Odoo 19 Community basado en las matrices de caracterizacion de procesos de EIGR Contratistas.

## Funcionalidad disponible

- Registro contractual y organizacional de obras.
- Correlativo automático `EIGR-AAAA-0000`.
- Flujo controlado: Borrador, Arranque, Planificación, Ejecución, Cierre y Cerrada.
- Cancelación y reapertura controladas.
- Avance físico y fechas planificadas/reales.
- Vista kanban, lista, formulario, filtros y seguimiento en chatter.
- Roles Equipo de obra y Jefe de Control.
- Reglas multiempresa y visibilidad por asignacion.
- Obra ficticia para la demostracion academica.
- Pruebas automáticas del modelo, flujo, restricciones y permisos.
- Presupuestos versionados con aprobación del Presupuesto Meta.
- Partidas de Control con metrados, unidades, costos, precios y recursos.
- Cálculo automático de costo, venta, margen y peso porcentual por partida.
- Valorizaciónes periodicas con metrados planificados y ejecutados.
- Costos reales del período y acumulados por partida.
- Indicadores de avance, desviación, valorización y CPI.
- Vista gráfica para la Curva S de avance planificado frente a avance real.
- Requerimientos de materiales, equipos, servicios y subcontratos.
- Circuito de aprobación, orden, recepción parcial y recepción total.
- Seguimiento de cantidades y costos estimados, ordenados y recibidos.
- Expediente y checklist documental de cierre con meta minima de 95%.
- Aprobación final que cierra automáticamente la obra.
- Tablero ejecutivo de obras.
- Reporte ejecutivo HTML imprimible desde Odoo o guardable como PDF desde el navegador.

El alcance funcional principal del prototipo academico queda completado.

## Avisos de trabajo pendiente

Una tarea automática revisa cada hora los requerimientos enviados sin aprobar, las entregas atrasadas y los expedientes de cierre incompletos al llegar su fecha objetivo. Crea una actividad pendiente para el responsable y la retira cuando la condición deja de cumplirse. Si cambia el responsable o la fecha, actualiza la actividad existente.

## Registros operativos

El módulo incluye expedientes técnicos con revisión y aprobación, cronogramas, incidencias con flujo de atención y documentos de obra. El equipo solo ve registros de sus obras asignadas; Planeamiento gestiona expedientes y cronograma, el Residente gestiona incidencias y documentos, el Responsable General gestiona documentos, y el administrador tiene permisos completos. Los borradores antiguos de adelantos, costos, liquidaciones y otros controles quedaron fuera del alcance activo hasta definir sus reglas de negocio.

## Datos de demostración

La obra, el cliente y los documentos ficticios solo se instalan si la base de datos se crea con datos de demostración. Al actualizar una base donde ya estaban instalados, los registros anteriores permanecen; revise la obra `EIGR-DEMO-001` y archívela manualmente si no debe aparecer entre las obras reales. No elimine en bloque registros vinculados que hayan sido utilizados.

## Valorizaciones

Apruebe las valorizaciones por fecha de corte, de la más antigua a la más reciente. El módulo impide aprobar una valorización anterior a otra ya aprobada y toma el avance físico de la última valorización aprobada. Al actualizar desde una versión anterior, también corrige el porcentaje de las obras que ya tienen valorizaciones aprobadas.

## Compras y costos contables

El módulo requiere Compras, Inventario y Contabilidad de Odoo. En un requerimiento nuevo, asigne un producto Odoo a cada recurso antes de enviarlo. Tras aprobarlo, seleccione proveedor y pulse **Crear cotización Odoo**. EIGR crea una cuenta analítica para la obra si aún no existe y asigna su distribución a las líneas de compra. Al confirmar la orden, EIGR toma la cantidad y el precio real; al validar recepciones de Inventario, toma las cantidades recibidas. Para servicios o productos con recepción manual, registre la cantidad recibida en la línea de compra. También puede usar **Actualizar desde compra** para reconciliar cambios hechos en Odoo. Las compras antiguas con referencia manual siguen funcionando.

El campo **Compras facturadas** suma los apuntes analíticos de facturas de proveedor publicadas, incluidas notas de crédito. Para que se contabilice un gasto, la factura debe conservar la distribución analítica de la obra. El saldo compara este costo contable con el costo del Presupuesto Meta; los costos capturados manualmente en valorizaciones permanecen como indicador operativo separado.

## Informe para el cliente

El menú de impresión de la obra incluye **Informe de Avance para Cliente** en PDF. Muestra fase, avance físico, última valorización aprobada y cronograma sin presupuestos ni costos internos. El Jefe de Control puede aprobar documentos con imágenes para incluirlos; si se cambian sus archivos, la aprobación se retira. El Responsable General puede usar **Enviar informe al cliente** para abrir un correo con el PDF adjunto y revisarlo antes de enviarlo. Es necesario que el cliente tenga correo y que la instalación pueda generar PDF.

## Hitos y retrasos

El cronograma admite responsable, marca de hito y actividad predecesora. Planeamiento puede completar una actividad cuando su predecesora está terminada. La tarea automática existente crea actividades para hitos o actividades vencidos y retira el aviso al completarlos. Las dependencias circulares o entre obras distintas se rechazan.
