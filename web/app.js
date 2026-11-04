/* ==========================================================================
   TAIS Quiz — lógica de la interfaz
   Vanilla JS, sin dependencias. Habla con la API del servidor local.
   ========================================================================== */

(() => {
  'use strict';

  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => Array.from(raiz.querySelectorAll(sel));

  const esc = (valor) =>
    String(valor ?? '').replace(/[&<>"']/g, (caracter) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[caracter]));

  const DIFICULTAD = { facil: 'Fácil', media: 'Media', dificil: 'Difícil' };
  const CLAVE_BORRADOR = 'tais-borrador-v1';
  const CLAVE_TEMA = 'tais-tema';

  const estado = {
    vista: 'inicio',
    config: {
      modo: 'examen',
      practicaCantidad: 10,
      practicaTema: '',
      practicaDesarrollo: false,
      temaTema: '',
      temaMc: 10,
      temaDesarrollo: 1,
      usarIA: true,
    },
    spec: null,
    banco: null,
    temas: [],
    corrector: null,
    examen: null,
    indice: 0,
    respuestas: { mc: {}, desarrollo: {} },
    resultado: null,
    filtro: 'todas',
    reloj: { intervalo: null, inicio: 0, limiteMs: 0, avisado: false },
    enviando: false,
    cargando: 0,
  };

  /* ------------------------------------------------------------- utilidades */

  async function api(ruta, opciones = {}) {
    const config = { ...opciones, headers: { ...(opciones.headers || {}) } };
    if (config.cuerpo !== undefined) {
      config.method = 'POST';
      config.headers['Content-Type'] = 'application/json';
      config.body = JSON.stringify(config.cuerpo);
      delete config.cuerpo;
    }
    const respuesta = await fetch(ruta, config);
    const texto = await respuesta.text();
    let datos = null;
    if (texto) {
      try {
        datos = JSON.parse(texto);
      } catch (error) {
        throw new Error(`El servidor devolvió una respuesta inesperada (${respuesta.status}).`);
      }
    }
    if (!respuesta.ok) {
      throw new Error((datos && datos.error) || `Error ${respuesta.status} del servidor.`);
    }
    return datos;
  }

  let temporizadorToast = null;
  function toast(mensaje, esError = false) {
    const caja = $('#toast');
    caja.textContent = mensaje;
    caja.classList.remove('oculto', 'error');
    if (esError) caja.classList.add('error');
    clearTimeout(temporizadorToast);
    temporizadorToast = setTimeout(() => caja.classList.add('oculto'), 3800);
  }

  function mostrarCarga(mostrar, mensaje = 'Procesando…') {
    let capa = $('#capa-carga');
    if (!mostrar) {
      if (capa) capa.remove();
      return;
    }
    if (!capa) {
      capa = document.createElement('div');
      capa.id = 'capa-carga';
      capa.className = 'capa-carga';
      capa.innerHTML = '<div class="caja-carga"><div class="spinner"></div><span></span></div>';
      document.body.appendChild(capa);
    }
    $('span', capa).textContent = mensaje;
  }

  function nombreTema(clave) {
    const encontrado = estado.temas.find((t) => t.clave === clave);
    return encontrado ? encontrado.nombre : clave;
  }

  function palabras(texto) {
    return (texto || '').trim().split(/\s+/).filter(Boolean).length;
  }

  function formatoFecha(iso) {
    if (!iso) return '';
    const fecha = new Date(iso);
    if (Number.isNaN(fecha.getTime())) return iso;
    return fecha.toLocaleString('es-AR', {
      day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  }

  function claseNota(nota) {
    if (nota >= 70) return 'ok';
    if (nota >= 50) return 'medio';
    return 'mal';
  }

  /* ------------------------------------------------------------------ vistas */

  function mostrarVista(nombre) {
    estado.vista = nombre;
    $$('.vista').forEach((seccion) => seccion.classList.add('oculto'));
    const vista = $(`#vista-${nombre}`);
    if (vista) vista.classList.remove('oculto');
    $$('.enlace').forEach((enlace) => enlace.classList.toggle('activo', enlace.dataset.nav === nombre));
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (nombre === 'historial') cargarHistorial();
  }

  /* --------------------------------------------------------------- arranque */

  async function iniciar() {
    aplicarTema(localStorage.getItem(CLAVE_TEMA) || 'oscuro');
    enlazarEventos();
    try {
      await cargarEstado();
    } catch (error) {
      toast('No se pudo cargar el estado del servidor: ' + error.message, true);
    }
    revisarBorrador();
  }

  async function cargarEstado() {
    const datos = await api('/api/estado');
    estado.spec = datos.especificacion;
    estado.banco = datos.banco;
    estado.temas = datos.temas;
    estado.corrector = datos.corrector;
    renderCobertura();
    renderBadgeIA();
    poblarSelects();
    actualizarDetalleExamen();
    const total = estado.spec.mc_por_tema
      ? Object.values(estado.spec.mc_por_tema).reduce((a, b) => a + b, 0)
      : 0;
    $('#nota-config').textContent =
      `Banco actual: ${estado.banco.total_mc} preguntas de múltiple opción y ` +
      `${estado.banco.total_desarrollo} de desarrollo. ` +
      `Cada intento evita las preguntas usadas en los últimos exámenes.`;
    $('#detalle-examen').textContent =
      `${total} múltiple opción + ${estado.spec.desarrollo_total} desarrollo`;
  }

  function renderBadgeIA() {
    const badge = $('#badge-ia');
    const info = estado.corrector || {};
    if (info.disponible) {
      badge.textContent = `IA local: ${info.modelo || 'lista'}`;
      badge.classList.add('ok');
      badge.classList.remove('sin');
      badge.title = `${info.proveedor} · ${info.url}\n${info.detalle || ''}`;
    } else {
      badge.textContent = 'IA local: apagada';
      badge.classList.add('sin');
      badge.classList.remove('ok');
      badge.title = (info.detalle || 'No se detectó un modelo local.') +
        '\nEl desarrollo se corrige con criterios y palabras clave.';
    }
  }

  function renderCobertura() {
    const contenedor = $('#cobertura');
    if (!estado.banco) return;
    const porTema = estado.banco.por_tema || {};
    const maximo = Math.max(1, ...Object.values(porTema).map((f) => f.mc));
    contenedor.innerHTML = Object.entries(porTema)
      .map(([clave, fila]) => `
        <div class="fila-cobertura">
          <div class="titulo-fila">
            <span>${esc(nombreTema(clave))}</span>
            <b>${fila.mc} MC · ${fila.desarrollo} dev</b>
          </div>
          <div class="barra-fina" title="${fila.mc} preguntas de múltiple opción">
            <span style="--pct:${Math.round((fila.mc / maximo) * 100)}"></span>
          </div>
        </div>`)
      .join('');
  }

  function poblarSelects() {
    const opciones = estado.temas
      .map((t) => `<option value="${esc(t.clave)}">${esc(t.nombre)}</option>`)
      .join('');
    const practica = $('#practica-tema');
    practica.innerHTML = `<option value="">Todos los temas</option>${opciones}`;
    practica.value = estado.config.practicaTema;
    const tema = $('#tema-tema');
    tema.innerHTML = opciones;
    estado.config.temaTema = estado.config.temaTema || (estado.temas[0] ? estado.temas[0].clave : '');
    tema.value = estado.config.temaTema;
  }

  function actualizarDetalleExamen() {
    if (!estado.spec) return;
    const total = Object.values(estado.spec.mc_por_tema || {}).reduce((a, b) => a + b, 0);
    $('#detalle-examen').textContent = `${total} múltiple opción + ${estado.spec.desarrollo_total} desarrollo`;
  }

  /* --------------------------------------------------------------- configuración */

  function seleccionarModo(modo) {
    estado.config.modo = modo;
    $$('.modo').forEach((boton) => {
      const activo = boton.dataset.modo === modo;
      boton.classList.toggle('activo', activo);
      boton.setAttribute('aria-checked', String(activo));
    });
    $('#campos-practica').classList.toggle('oculto', modo !== 'practica');
    $('#campos-tema').classList.toggle('oculto', modo !== 'tema');
    actualizarNota();
  }

  function actualizarNota() {
    const nota = $('#nota-config');
    if (estado.config.modo === 'practica') {
      nota.textContent = 'La práctica muestra la respuesta correcta y la explicación en el momento.';
    } else if (estado.config.modo === 'tema') {
      nota.textContent = 'Elegí un tema para concentrarte. La corrección es igual que en el examen completo.';
    } else {
      const total = Object.values((estado.spec && estado.spec.mc_por_tema) || {}).reduce((a, b) => a + b, 0);
      nota.textContent =
        `Examen completo: ${total} de múltiple opción y ${estado.spec ? estado.spec.desarrollo_total : 5} de desarrollo, ` +
        'con el peso 60/40 y tiempo sugerido de ' + (estado.spec ? estado.spec.tiempo_limite_min : 100) + ' minutos.';
    }
  }

  function construirSolicitud() {
    const cfg = estado.config;
    if (cfg.modo === 'practica') {
      return {
        modo: 'practica',
        cantidad: Number($('#practica-cantidad').value),
        tema: $('#practica-tema').value || null,
        incluir_desarrollo: $('#practica-desarrollo').checked,
      };
    }
    if (cfg.modo === 'tema') {
      const tema = $('#tema-tema').value;
      if (!tema) throw new Error('Elegí un tema para empezar.');
      const mc = Number($('#tema-mc').value);
      const desarrollo = Number($('#tema-desarrollo').value);
      return { modo: 'examen', temas: [tema], mc_por_tema: { [tema]: mc }, desarrollo };
    }
    return { modo: 'examen' };
  }

  /* ---------------------------------------------------------------- examen */

  async function comenzar() {
    let solicitud;
    try {
      solicitud = construirSolicitud();
    } catch (error) {
      toast(error.message, true);
      return;
    }
    mostrarCarga(true, solicitud.modo === 'practica' ? 'Preparando la práctica…' : 'Generando un examen nuevo…');
    try {
      const examen = await api('/api/examen', { cuerpo: solicitud });
      estado.examen = examen;
      estado.indice = 0;
      estado.respuestas = { mc: {}, desarrollo: {} };
      estado.resultado = null;
      empezarReloj();
      mostrarVista('examen');
      renderExamen();
      guardarBorrador();
    } catch (error) {
      toast('No se pudo generar el examen: ' + error.message, true);
    } finally {
      mostrarCarga(false);
    }
  }

  function esPractica() {
    return Boolean(estado.examen && estado.examen.modo === 'practica');
  }

  function renderExamen() {
    const examen = estado.examen;
    if (!examen) return;
    const total = examen.preguntas.length;
    estado.indice = Math.max(0, Math.min(estado.indice, total - 1));
    const pregunta = examen.preguntas[estado.indice];
    const contenedor = $('#tarjeta-pregunta');

    const chips = [
      `<span class="chip">${esc(nombreTema(pregunta.tema))}</span>`,
      `<span class="chip suave">${pregunta.tipo === 'mc' ? 'Múltiple opción' : 'Desarrollo'}</span>`,
      `<span class="chip suave">${esc(DIFICULTAD[pregunta.dificultad] || pregunta.dificultad || '')}</span>`,
      pregunta.subtema ? `<span class="chip suave">${esc(String(pregunta.subtema).replace(/-/g, ' '))}</span>` : '',
    ].join('');

    contenedor.innerHTML = `<div class="encabezado-pregunta">${chips}</div>`;
    if (pregunta.tipo === 'mc') {
      renderMC(pregunta, contenedor);
    } else {
      renderDesarrollo(pregunta, contenedor);
    }
    actualizarProgreso();
    actualizarNavegacion();
  }

  function renderMC(pregunta, contenedor) {
    const elegida = estado.respuestas.mc[pregunta.id];
    const practica = esPractica();
    const corregida = practica && elegida !== undefined;
    const enunciado = document.createElement('h2');
    enunciado.className = 'enunciado';
    enunciado.textContent = pregunta.pregunta;
    contenedor.appendChild(enunciado);

    const lista = document.createElement('div');
    lista.className = 'opciones';
    pregunta.opciones.forEach((opcion, indice) => {
      const boton = document.createElement('button');
      boton.type = 'button';
      boton.className = 'opcion';
      boton.dataset.opcion = String(indice);
      boton.innerHTML = `<span class="letra">${esc(opcion.letra)}</span><span>${esc(opcion.texto)}</span>`;
      if (elegida === indice) boton.classList.add('elegida');
      if (corregida) {
        if (indice === pregunta.correcta) boton.classList.add('correcta');
        else if (indice === elegida) boton.classList.add('incorrecta');
        boton.disabled = true;
      }
      boton.addEventListener('click', () => seleccionarOpcion(indice));
      lista.appendChild(boton);
    });
    contenedor.appendChild(lista);

    if (corregida) {
      const caja = document.createElement('div');
      caja.className = 'explicacion';
      const acerto = elegida === pregunta.correcta;
      const fuente = pregunta.referencia ? `<span class="fuente">Fuente: ${esc(pregunta.referencia)}</span>` : '';
      caja.innerHTML =
        `<strong>${acerto ? 'Correcta.' : `Incorrecta: la respuesta era ${esc(pregunta.opciones[pregunta.correcta].letra)}.`}</strong> ` +
        `${esc(pregunta.explicacion || '')}${fuente}`;
      contenedor.appendChild(caja);
    }
  }

  function renderDesarrollo(pregunta, contenedor) {
    const enunciado = document.createElement('h2');
    enunciado.className = 'enunciado';
    enunciado.textContent = pregunta.pregunta;
    contenedor.appendChild(enunciado);

    const ayuda = document.createElement('p');
    ayuda.className = 'nota';
    ayuda.textContent = `Desarrollá la respuesta en 5 a 10 líneas. Tiempo sugerido: ${
      pregunta.tiempo_sugerido_min || 5
    } minutos.`;
    contenedor.appendChild(ayuda);

    const area = document.createElement('textarea');
    area.id = 'area-desarrollo';
    area.placeholder = 'Escribí tu respuesta acá…';
    area.value = estado.respuestas.desarrollo[pregunta.id] || '';
    area.addEventListener('input', () => {
      estado.respuestas.desarrollo[pregunta.id] = area.value;
      actualizarContadorPalabras();
      actualizarProgreso();
      actualizarNavegacion();
      programarGuardado();
    });
    contenedor.appendChild(area);

    const contador = document.createElement('div');
    contador.className = 'contador-palabras';
    contador.innerHTML = `<span id="contador-palabras">0 palabras</span><span>Se guarda automáticamente</span>`;
    contenedor.appendChild(contador);

    if (esPractica()) {
      const acciones = document.createElement('div');
      acciones.className = 'acciones';
      acciones.innerHTML = `<button id="btn-corregir-dev" class="boton fantasma">Corregir esta respuesta</button>`;
      contenedor.appendChild(acciones);
      $('#btn-corregir-dev', contenedor).addEventListener('click', () => corregirDesarrolloActual());
    }

    const feedback = document.createElement('div');
    feedback.id = 'feedback-dev';
    contenedor.appendChild(feedback);

    actualizarContadorPalabras();
  }

  function actualizarContadorPalabras() {
    const area = $('#area-desarrollo');
    const contador = $('#contador-palabras');
    if (!area || !contador) return;
    const cantidad = palabras(area.value);
    contador.textContent = `${cantidad} ${cantidad === 1 ? 'palabra' : 'palabras'}`;
  }

  function seleccionarOpcion(indice) {
    const pregunta = estado.examen.preguntas[estado.indice];
    if (!pregunta || pregunta.tipo !== 'mc') return;
    if (esPractica() && estado.respuestas.mc[pregunta.id] !== undefined) return;
    estado.respuestas.mc[pregunta.id] = indice;
    guardarBorrador();
    renderExamen();
  }

  async function corregirDesarrolloActual() {
    const pregunta = estado.examen.preguntas[estado.indice];
    const texto = (estado.respuestas.desarrollo[pregunta.id] || '').trim();
    if (palabras(texto) < 5) {
      toast('Escribí al menos unas frases antes de corregir.', true);
      return;
    }
    const boton = $('#btn-corregir-dev');
    if (boton) { boton.disabled = true; boton.textContent = 'Corrigiendo…'; }
    try {
      const datos = await api('/api/corregir-desarrollo', {
        cuerpo: { pregunta_id: pregunta.id, respuesta: texto, usar_llm: estado.config.usarIA },
      });
      pintarCorreccionDesarrollo(datos);
    } catch (error) {
      toast('No se pudo corregir: ' + error.message, true);
    } finally {
      if (boton) { boton.disabled = false; boton.textContent = 'Corregir esta respuesta'; }
    }
  }

  function pintarCorreccionDesarrollo(datos) {
    const caja = $('#feedback-dev');
    if (!caja) return;
    const correccion = datos.correccion || {};
    const porcentaje = Math.round((correccion.puntaje || 0) * 100);
    const clase = porcentaje >= 70 ? 'ok' : porcentaje >= 40 ? 'medio' : 'mal';
    const criterios = (correccion.criterios || []).map((c) => `
      <div class="criterio ${c.cumplido ? 'cumplido' : ''}">
        <span class="marca">${c.cumplido ? '✓' : '·'}</span>
        <span><span class="peso">(${Number(c.peso).toFixed(2)})</span> ${esc(c.descripcion)}
        <br><small class="nota">${esc(c.detalle || '')}</small></span>
      </div>`).join('');
    caja.innerHTML = `
      <div class="caja">
        <span class="etiqueta-puntaje ${clase}">${porcentaje}% · ${esc(correccion.modo === 'llm' ? 'modelo local' : 'criterios')}</span>
        <p>${esc(correccion.comentario || '')}</p>
        ${criterios ? `<div class="criterios">${criterios}</div>` : ''}
        <h4>Respuesta modelo</h4>
        <p>${esc(datos.respuesta_modelo || '')}</p>
        <span class="fuente">Fuente: ${esc(datos.referencia || '')}</span>
      </div>`;
  }

  function actualizarProgreso() {
    const examen = estado.examen;
    if (!examen) return;
    const total = examen.preguntas.length;
    let respondidas = 0;
    examen.preguntas.forEach((pregunta) => {
      if (pregunta.tipo === 'mc') {
        if (estado.respuestas.mc[pregunta.id] !== undefined) respondidas += 1;
      } else if (palabras(estado.respuestas.desarrollo[pregunta.id]) > 0) {
        respondidas += 1;
      }
    });
    const porcentaje = total ? Math.round((respondidas / total) * 100) : 0;
    $('#progreso-relleno').style.width = `${porcentaje}%`;
    const barra = $('.progreso');
    if (barra) barra.setAttribute('aria-valuenow', String(porcentaje));
    const prefijo = esPractica() ? 'Práctica' : 'Pregunta';
    $('#contador-preguntas').textContent = `${prefijo} ${estado.indice + 1} de ${total}`;
  }

  function actualizarNavegacion() {
    const examen = estado.examen;
    if (!examen) return;
    const total = examen.preguntas.length;
    $('#btn-anterior').disabled = estado.indice === 0;
    const boton = $('#btn-siguiente');
    boton.textContent = estado.indice === total - 1 ? 'Finalizar y corregir' : 'Siguiente →';

    const mapa = $('#puntos');
    mapa.innerHTML = '';
    examen.preguntas.forEach((pregunta, indice) => {
      const respondida = pregunta.tipo === 'mc'
        ? estado.respuestas.mc[pregunta.id] !== undefined
        : palabras(estado.respuestas.desarrollo[pregunta.id]) > 0;
      const botonPunto = document.createElement('button');
      botonPunto.type = 'button';
      botonPunto.className = 'punto' + (respondida ? ' respondida' : '') +
        (indice === estado.indice ? ' actual' : '') + (pregunta.tipo === 'desarrollo' ? ' dev' : '');
      botonPunto.textContent = String(indice + 1);
      botonPunto.title = pregunta.tipo === 'mc' ? 'Múltiple opción' : 'Desarrollo';
      botonPunto.addEventListener('click', () => irA(indice));
      mapa.appendChild(botonPunto);
    });
  }

  function irA(indice) {
    if (!estado.examen) return;
    estado.indice = Math.max(0, Math.min(indice, estado.examen.preguntas.length - 1));
    renderExamen();
    guardarBorrador();
  }

  /* ------------------------------------------------------------------ reloj */

  function empezarReloj() {
    detenerReloj();
    const especificacion = estado.examen.especificacion || {};
    const minutos = Number(especificacion.tiempo_limite_min || 0);
    const practica = esPractica();
    estado.reloj.inicio = Date.now();
    estado.reloj.limiteMs = !practica && minutos > 0 ? minutos * 60000 : 0;
    estado.reloj.avisado = false;
    $('#reloj').classList.remove('oculto');
    pintarReloj();
    estado.reloj.intervalo = setInterval(pintarReloj, 1000);
  }

  function detenerReloj() {
    if (estado.reloj.intervalo) clearInterval(estado.reloj.intervalo);
    estado.reloj.intervalo = null;
  }

  function pintarReloj() {
    const reloj = $('#reloj');
    if (!reloj) return;
    if (estado.reloj.limiteMs) {
      const restante = Math.max(0, estado.reloj.limiteMs - (Date.now() - estado.reloj.inicio));
      const segundos = Math.floor(restante / 1000);
      const mm = String(Math.floor(segundos / 60)).padStart(2, '0');
      const ss = String(segundos % 60).padStart(2, '0');
      reloj.textContent = `${mm}:${ss}`;
      reloj.classList.toggle('urgente', restante < 5 * 60000);
      reloj.title = 'Tiempo restante';
      if (restante === 0 && !estado.reloj.avisado) {
        estado.reloj.avisado = true;
        toast('Se terminó el tiempo: se corrige el examen con lo respondido.', true);
        finalizar(true);
      }
    } else {
      const transcurrido = Math.floor((Date.now() - estado.reloj.inicio) / 1000);
      const mm = String(Math.floor(transcurrido / 60)).padStart(2, '0');
      const ss = String(transcurrido % 60).padStart(2, '0');
      reloj.textContent = `${mm}:${ss}`;
      reloj.classList.remove('urgente');
      reloj.title = 'Tiempo transcurrido';
    }
  }

  /* ------------------------------------------------------------- corrección */

  async function finalizar(automatico = false) {
    if (estado.enviando || !estado.examen) return;
    const total = estado.examen.preguntas.length;
    const sinResponder = estado.examen.preguntas.filter((pregunta) => (
      pregunta.tipo === 'mc'
        ? estado.respuestas.mc[pregunta.id] === undefined
        : palabras(estado.respuestas.desarrollo[pregunta.id]) === 0
    )).length;

    if (!automatico && sinResponder > 0) {
      const mensaje = `Tenés ${sinResponder} pregunta${sinResponder === 1 ? '' : 's'} sin responder. ` +
        '¿Corregir igual?';
      if (!window.confirm(mensaje)) return;
    }

    estado.enviando = true;
    mostrarCarga(true, 'Corrigiendo el examen…');
    try {
      const resultado = await api('/api/corregir', {
        cuerpo: {
          examen_id: estado.examen.id,
          mc: estado.respuestas.mc,
          desarrollo: estado.respuestas.desarrollo,
          usar_llm: estado.config.usarIA,
        },
      });
      detenerReloj();
      estado.resultado = resultado;
      borrarBorrador();
      mostrarVista('resultados');
      renderResultados(resultado);
    } catch (error) {
      toast('No se pudo corregir: ' + error.message, true);
    } finally {
      estado.enviando = false;
      mostrarCarga(false);
    }
  }

  function renderResultados(resultado) {
    estado.resultado = resultado;
    estado.filtro = 'todas';
    $$('.filtro').forEach((boton) => boton.classList.toggle('activo', boton.dataset.filtro === 'todas'));
    const resumen = resultado.resumen || {};
    const nota = Math.round(Number(resumen.nota_100 || 0));
    const clase = claseNota(nota);
    const color = clase === 'ok' ? 'var(--ok)' : clase === 'medio' ? 'var(--aviso)' : 'var(--mal)';
    const temas = Object.entries(resumen.por_tema || {}).map(([clave, fila]) => `
      <div class="tema-resultado">
        <span>${esc(nombreTema(clave))}</span>
        <div class="barra-fina"><span style="--pct:${fila.porcentaje}"></span></div>
        <b>${fila.porcentaje}%</b>
      </div>`).join('');

    $('#resumen-resultados').innerHTML = `
      <div class="tarjeta">
        <div class="resumen">
          <div class="anillo" style="--pct:${nota};--color:${color}">
            <div class="valor"><b>${nota}</b><small>de 100</small></div>
          </div>
          <div class="datos">
            <h1>${esc(resumen.nivel || 'Resultado')}</h1>
            <p class="nivel">${esc(resultado.nombre || 'Examen')} · ${formatoFecha(resultado.creado)} ·
              corrección ${esc(resumen.modo_correccion === 'llm' ? 'con modelo local' : 'por criterios')}</p>
            <div class="metricas">
              <div class="metrica"><span class="rotulo">Múltiple opción</span>
                <span class="dato">${resumen.mc_aciertos}/${resumen.mc_total}
                <small>· ${resumen.mc_porcentaje}%</small></span></div>
              <div class="metrica"><span class="rotulo">Desarrollo</span>
                <span class="dato">${resumen.desarrollo_puntaje}/${resumen.desarrollo_total}
                <small>· ${resumen.desarrollo_porcentaje}%</small></span></div>
              <div class="metrica"><span class="rotulo">Nota /10</span>
                <span class="dato">${resumen.nota_10}</span></div>
            </div>
            ${temas ? `<div class="temas-resultado">${temas}</div>` : ''}
          </div>
        </div>
      </div>`;
    renderDetalle();
  }

  function renderDetalle() {
    const resultado = estado.resultado;
    if (!resultado) return;
    const filtro = estado.filtro;
    const bloques = [];

    resultado.mc.forEach((item, indice) => {
      const numero = indice + 1;
      const incluir = filtro !== 'desarrollo' && (filtro === 'todas' || !item.es_correcta);
      if (!incluir) return;
      bloques.push(itemMC(item, numero, !item.es_correcta));
    });
    resultado.desarrollo.forEach((item, indice) => {
      const numero = resultado.mc.length + indice + 1;
      const incluir = filtro !== 'incorrectas' || item.correccion.puntaje < 0.999;
      if (!incluir) return;
      bloques.push(itemDesarrollo(item, numero, filtro !== 'incorrectas'));
    });

    $('#detalle-resultados').innerHTML = bloques.length
      ? bloques.join('')
      : `<div class="tarjeta"><p class="nota">No hay preguntas para este filtro. ¡Buen trabajo!</p></div>`;
  }

  function itemMC(item, numero, abierto) {
    const clase = item.es_correcta ? 'bien' : 'incompleta';
    const veredicto = item.es_correcta ? '<span class="veredicto ok">✓</span>'
      : '<span class="veredicto mal">✗</span>';
    const respuestaTexto = item.es_correcta
      ? 'Correcta'
      : item.elegida === null
        ? 'Sin responder'
        : `Elegiste ${item.opciones[item.elegida] ? item.opciones[item.elegida].letra : '—'}`;
    const opciones = item.opciones.map((opcion) => {
      const clases = ['opcion-revision'];
      if (opcion.es_correcta) clases.push('correcta');
      if (item.elegida !== null && opcion.letra === item.opciones[item.elegida].letra && !opcion.es_correcta) {
        clases.push('elegida');
      }
      const porque = !opcion.es_correcta && opcion.porque_no
        ? `<span class="porque">${esc(opcion.porque_no)}</span>` : '';
      return `<div class="${clases.join(' ')}"><span class="letra">${esc(opcion.letra)}</span>
        <span>${esc(opcion.texto)}${porque}</span></div>`;
    }).join('');

    return `
      <details class="item-resultado ${clase}" ${abierto ? 'open' : ''}>
        <summary>
          ${veredicto}
          <span>
            <span class="titulo-item">${numero}. ${esc(item.pregunta)}</span>
            <span class="meta-item">${esc(nombreTema(item.tema))} · ${esc(DIFICULTAD[item.dificultad] || item.dificultad)} ·
              ${esc(respuestaTexto)}</span>
          </span>
        </summary>
        <div class="cuerpo">
          <div class="opciones-revision">${opciones}</div>
          <div class="caja">
            <h4>Por qué</h4>
            <p>${esc(item.explicacion)}</p>
            <span class="fuente">Fuente: ${esc(item.referencia || '')}</span>
          </div>
        </div>
      </details>`;
  }

  function itemDesarrollo(item, numero, abierto) {
    const correccion = item.correccion || {};
    const porcentaje = Math.round(Number(correccion.puntaje || 0) * 100);
    const clase = porcentaje >= 70 ? 'ok' : porcentaje >= 40 ? 'medio' : 'mal';
    const claseItem = porcentaje >= 70 ? 'bien' : porcentaje >= 40 ? 'parcial' : 'incompleta';
    const criterios = (correccion.criterios || []).map((criterio) => `
      <div class="criterio ${criterio.cumplido ? 'cumplido' : ''}">
        <span class="marca">${criterio.cumplido ? '✓' : '·'}</span>
        <span><span class="peso">(${Number(criterio.peso).toFixed(2)})</span>
          ${esc(criterio.descripcion)}
          <br><small class="nota">${esc(criterio.detalle || '')}</small></span>
      </div>`).join('');
    const error = correccion.error
      ? `<p class="nota">Aviso: ${esc(correccion.error)}</p>` : '';

    return `
      <details class="item-resultado ${claseItem}" ${abierto ? 'open' : ''}>
        <summary>
          <span class="veredicto ${clase === 'mal' ? 'mal' : clase === 'medio' ? 'medio' : 'ok'}">${porcentaje >= 70 ? '✓' : porcentaje >= 40 ? '~' : '✗'}</span>
          <span>
            <span class="titulo-item">${numero}. ${esc(item.pregunta)}</span>
            <span class="meta-item">${esc(nombreTema(item.tema))} · Desarrollo ·
              ${porcentaje}% · ${correccion.modo === 'llm' ? 'modelo local' : 'criterios'}</span>
          </span>
        </summary>
        <div class="cuerpo">
          <div class="caja">
            <h4>Tu respuesta</h4>
            <p>${esc(item.respuesta || 'Sin responder')}</p>
          </div>
          <p>${esc(correccion.comentario || '')}</p>
          ${error}
          ${criterios ? `<div class="criterios">${criterios}</div>` : ''}
          <div class="caja">
            <h4>Respuesta modelo</h4>
            <p>${esc(item.respuesta_modelo || '')}</p>
          </div>
          <span class="fuente">Fuente: ${esc(item.referencia || '')}</span>
        </div>
      </details>`;
  }

  /* ---------------------------------------------------------------- borrador */

  let temporizadorBorrador = null;

  function programarGuardado() {
    clearTimeout(temporizadorBorrador);
    temporizadorBorrador = setTimeout(guardarBorrador, 350);
  }

  function guardarBorrador() {
    if (!estado.examen) return;
    try {
      localStorage.setItem(CLAVE_BORRADOR, JSON.stringify({
        examen: estado.examen,
        respuestas: estado.respuestas,
        indice: estado.indice,
        guardado: Date.now(),
      }));
    } catch (error) {
      /* si no hay espacio, seguimos sin borrador */
    }
  }

  function borrarBorrador() {
    try { localStorage.removeItem(CLAVE_BORRADOR); } catch (error) { /* ignorar */ }
  }

  function revisarBorrador() {
    let datos = null;
    try {
      const crudo = localStorage.getItem(CLAVE_BORRADOR);
      if (!crudo) return;
      datos = JSON.parse(crudo);
    } catch (error) {
      return;
    }
    if (!datos || !datos.examen || !datos.examen.preguntas) {
      borrarBorrador();
      return;
    }
    const edadHoras = (Date.now() - (datos.guardado || 0)) / 3600000;
    if (edadHoras > 24) {
      borrarBorrador();
      return;
    }
    const aviso = $('#aviso-borrador');
    const cuando = formatoFecha(new Date(datos.guardado || Date.now()).toISOString());
    aviso.innerHTML = `
      <span>Tenés un intento sin terminar <strong>${esc(datos.examen.id)}</strong> (${esc(cuando)}),
      con ${Object.keys(datos.respuestas.mc || {}).length + Object.keys(datos.respuestas.desarrollo || {}).length}
      respuestas guardadas.</span>
      <div class="acciones">
        <button class="boton primario chico" id="btn-retomar">Retomar</button>
        <button class="boton fantasma chico" id="btn-descartar">Descartar</button>
      </div>`;
    aviso.classList.remove('oculto');
    $('#btn-retomar').addEventListener('click', () => {
      estado.examen = datos.examen;
      estado.respuestas = datos.respuestas;
      estado.indice = datos.indice || 0;
      estado.resultado = null;
      aviso.classList.add('oculto');
      empezarReloj();
      mostrarVista('examen');
      renderExamen();
      toast('Retomaste el intento guardado.');
    });
    $('#btn-descartar').addEventListener('click', () => {
      borrarBorrador();
      aviso.classList.add('oculto');
    });
  }

  /* --------------------------------------------------------------- historial */

  async function cargarHistorial() {
    const contenedor = $('#lista-historial');
    contenedor.innerHTML = '<div class="cargando">Cargando historial…</div>';
    try {
      const datos = await api('/api/historial');
      renderHistorial(datos.examenes || []);
    } catch (error) {
      contenedor.innerHTML = `<div class="tarjeta"><p class="nota">No se pudo cargar el historial: ${esc(error.message)}</p></div>`;
    }
  }

  function renderHistorial(intentos) {
    const contenedor = $('#lista-historial');
    if (!intentos.length) {
      contenedor.innerHTML = `<div class="tarjeta"><p class="nota">Todavía no hay intentos guardados.
        Hacé el primero y va a aparecer acá.</p></div>`;
      return;
    }
    contenedor.innerHTML = intentos.map((intento) => {
      const nota = Math.round(Number(intento.nota_100 || 0));
      return `
        <button class="intento" data-examen="${esc(intento.examen_id)}">
          <span class="nota-mini ${claseNota(nota)}">${nota}</span>
          <span class="detalle-intento">
            <strong>${esc(intento.nombre || 'Examen')}</strong>
            <small>${formatoFecha(intento.creado)} · ${esc(intento.nivel || '')} ·
              ${intento.mc_aciertos}/${intento.mc_total} MC · desarrollo ${intento.desarrollo_porcentaje}%</small>
          </span>
          <span class="flecha">→</span>
        </button>`;
    }).join('');
    $$('.intento', contenedor).forEach((boton) => {
      boton.addEventListener('click', () => abrirResultado(boton.dataset.examen));
    });
  }

  async function abrirResultado(idExamen) {
    mostrarCarga(true, 'Abriendo el intento…');
    try {
      const resultado = await api(`/api/resultado/${encodeURIComponent(idExamen)}`);
      estado.resultado = resultado;
      mostrarVista('resultados');
      renderResultados(resultado);
      $('#btn-descargar').dataset.examen = idExamen;
    } catch (error) {
      toast('No se pudo abrir el intento: ' + error.message, true);
    } finally {
      mostrarCarga(false);
    }
  }

  function descargarBoleta() {
    const id = (estado.resultado && estado.resultado.examen_id) || $('#btn-descargar').dataset.examen;
    if (!id) {
      toast('Corregí un examen primero.', true);
      return;
    }
    window.location.href = `/api/examen/${encodeURIComponent(id)}/boleta`;
  }

  /* -------------------------------------------------------------------- tema */

  function aplicarTema(tema) {
    document.documentElement.dataset.tema = tema;
    localStorage.setItem(CLAVE_TEMA, tema);
    const boton = $('#btn-tema');
    if (boton) boton.textContent = tema === 'claro' ? '☀' : '◐';
  }

  /* ----------------------------------------------------------------- eventos */

  function enlazarEventos() {
    $$('[data-nav]').forEach((elemento) => {
      elemento.addEventListener('click', (evento) => {
        evento.preventDefault();
        if (estado.vista === 'examen' && estado.examen) {
          if (!window.confirm('Salís del examen actual. El intento queda guardado para retomarlo, ¿continuar?')) return;
          guardarBorrador();
          detenerReloj();
        }
        mostrarVista(elemento.dataset.nav);
      });
    });

    $$('.modo').forEach((boton) => {
      boton.addEventListener('click', () => seleccionarModo(boton.dataset.modo));
    });

    $('#practica-cantidad').addEventListener('change', (e) => { estado.config.practicaCantidad = Number(e.target.value); });
    $('#practica-tema').addEventListener('change', (e) => { estado.config.practicaTema = e.target.value; });
    $('#practica-desarrollo').addEventListener('change', (e) => { estado.config.practicaDesarrollo = e.target.checked; });
    $('#tema-tema').addEventListener('change', (e) => { estado.config.temaTema = e.target.value; });
    $('#tema-mc').addEventListener('change', (e) => { estado.config.temaMc = Number(e.target.value); });
    $('#tema-desarrollo').addEventListener('change', (e) => { estado.config.temaDesarrollo = Number(e.target.value); });
    $('#usar-ia').addEventListener('change', (e) => { estado.config.usarIA = e.target.checked; });

    $('#btn-comenzar').addEventListener('click', comenzar);
    $('#btn-ver-historial').addEventListener('click', () => mostrarVista('historial'));
    $('#btn-tema').addEventListener('click', () => {
      aplicarTema(document.documentElement.dataset.tema === 'claro' ? 'oscuro' : 'claro');
    });

    $('#btn-siguiente').addEventListener('click', () => {
      const total = estado.examen ? estado.examen.preguntas.length : 0;
      if (estado.indice >= total - 1) finalizar();
      else irA(estado.indice + 1);
    });
    $('#btn-anterior').addEventListener('click', () => irA(estado.indice - 1));
    $('#btn-finalizar').addEventListener('click', () => finalizar());
    $('#btn-abandonar').addEventListener('click', () => {
      if (!estado.examen) return;
      if (!window.confirm('¿Abandonar el intento? Se guarda como borrador para retomarlo después.')) return;
      guardarBorrador();
      detenerReloj();
      mostrarVista('inicio');
    });

    $('#btn-descargar').addEventListener('click', descargarBoleta);
    $('#btn-nuevo').addEventListener('click', () => {
      detenerReloj();
      estado.examen = null;
      estado.resultado = null;
      mostrarVista('inicio');
      comenzar();
    });
    $('#btn-volver-inicio').addEventListener('click', () => {
      detenerReloj();
      mostrarVista('inicio');
    });

    $$('.filtro').forEach((boton) => {
      boton.addEventListener('click', () => {
        estado.filtro = boton.dataset.filtro;
        $$('.filtro').forEach((otro) => otro.classList.toggle('activo', otro === boton));
        renderDetalle();
      });
    });

    document.addEventListener('keydown', (evento) => {
      if (estado.vista !== 'examen' || !estado.examen) return;
      const objetivo = evento.target;
      if (objetivo && ['INPUT', 'TEXTAREA', 'SELECT'].includes(objetivo.tagName)) return;
      if (evento.ctrlKey || evento.metaKey || evento.altKey) return;
      const pregunta = estado.examen.preguntas[estado.indice];
      const tecla = evento.key.toLowerCase();
      if (pregunta && pregunta.tipo === 'mc') {
        const letras = ['a', 'b', 'c', 'd', 'e'];
        let indice = -1;
        if (letras.includes(tecla)) indice = letras.indexOf(tecla);
        else if (/^[1-5]$/.test(tecla)) indice = Number(tecla) - 1;
        if (indice >= 0 && indice < pregunta.opciones.length) {
          evento.preventDefault();
          seleccionarOpcion(indice);
          return;
        }
      }
      if (evento.key === 'ArrowRight') {
        evento.preventDefault();
        if (estado.indice < estado.examen.preguntas.length - 1) irA(estado.indice + 1);
      } else if (evento.key === 'ArrowLeft') {
        evento.preventDefault();
        if (estado.indice > 0) irA(estado.indice - 1);
      }
    });
  }

  document.addEventListener('DOMContentLoaded', iniciar);
})();
