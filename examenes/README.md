# Exámenes y boletas

Esta carpeta la crea la aplicación al generar exámenes. Guarda:

- `<id>.json`: el examen generado (preguntas y orden de opciones).
- `<id>-resultado.json`: la corrección completa.
- `boleta-<id>.md`: la boleta en Markdown.
- `historial.json`: cuántas veces se usó cada pregunta (para la rotación).

Los archivos están excluidos de Git (`.gitignore`) porque son datos personales de uso.
Se puede borrar el contenido sin afectar al banco de preguntas.
