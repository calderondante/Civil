# Dependencias y licencias

El código del estudio es nuevo; no se copió el código de Podcastfy, Kokoro ni PodAgent. No se cambia la licencia de la guía original ni se asigna una licencia de redistribución a su contenido.

Next.js, React, FastAPI, SQLAlchemy, httpx y varios paquetes Python publican licencias permisivas; conservar los avisos incluidos en sus distribuciones. Revisar lockfiles y sus licencias antes de redistribuir comercialmente una imagen completa. FFmpeg puede estar construido con componentes GPL: el contenedor instala el paquete Debian con `libmp3lame`; revisar su configuración y avisos.

`espeakng-loader` incluye eSpeak NG. El motor es GPL-3.0-or-later; el wrapper no elimina esas obligaciones. Se usa sólo como proveedor local de prueba. Si se distribuye una imagen/binario con esta biblioteca, entregar avisos, licencia y fuente correspondiente según los términos aplicables; inspeccionar la versión y origen del wheel exacto fijado en el lock. Fuentes: [eSpeak NG](https://github.com/espeak-ng/espeak-ng), [COPYING](https://github.com/espeak-ng/espeak-ng/blob/master/COPYING), [espeakng-loader](https://pypi.org/project/espeakng-loader/). No presentar todo el conjunto como Apache/MIT por la licencia del wrapper. El texto y los audios de salida no son automáticamente código del motor.

Los derechos sobre materiales de estudio, locutores, clones, modelos, datasets y música son independientes del código. El MVP no clona voces, no incorpora música y no distribuye pesos neuronales. Para Gemini y ElevenLabs, verificar contrato y plan, tratamiento de datos y derechos de cada voz. No se asume licencia comercial gratuita de una API.
