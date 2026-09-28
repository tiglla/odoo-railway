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
