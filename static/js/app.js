const { createApp, defineComponent } = Vue;

// Wrapper for fetch to handle session expiration
async function secureFetch(url, options) {
  const response = await fetch(url, options);
  if (response.status === 401) {
    // Session expired, redirect to login
    window.location.href = '/login';
    // Throw an error to stop further processing in the promise chain
    throw new Error('Session expired');
  }
  return response;
}

// Helper function to load templates from external files
const loadTemplate = async (name) => {
  const response = await secureFetch(`/view/pages/${name}.html`);
  if (!response.ok) throw new Error(`Could not load template ${name}`);
  return await response.text();
};


const FieldRenderer = defineComponent({
  name: 'FieldRenderer',
  // 1. Accetta la nuova prop 'disabled'
  props: ['model', 'keyName', 'schema', 'label', 'disabled'],
  data() {
    return {
      showPassword: false,
      uid: 'field-' + Math.random().toString(36).substring(2, 9)
    };
  },
  computed: {
    value: {
      get() { return this.model ? this.model[this.keyName] : null; },
      set(v) { if (this.model) this.model[this.keyName] = v; }
    },
    fieldType() { return this.schema?.[this.keyName]?.type || 'text'; },
    options() { return this.schema?.[this.keyName]?.options || []; }
  },
  // 2. Applica la prop agli elementi del template
  template: `
    <div class="mb-3">
      <select v-if="fieldType === 'select'" v-model="value" class="form-select" :disabled="disabled">
        <option v-for="(opt, index) in options" :value="index">[[ opt ]]</option>
      </select>
      <input v-else-if="fieldType === 'number'" type="number" class="form-control" v-model.number="value" :disabled="disabled">
      <div v-else-if="fieldType === 'password'" class="input-group">
        <input :type="showPassword ? 'text' : 'password'" class="form-control" v-model="value" :disabled="disabled">
        <button class="btn btn-outline-secondary" type="button" @click="showPassword = !showPassword" :disabled="disabled">
          <i class="bi" :class="showPassword ? 'bi-eye-slash' : 'bi-eye'"></i>
        </button>
      </div>
      <div v-else-if="fieldType === 'boolean'" class="form-check form-switch">
        <input class="form-check-input" type="checkbox" role="switch" v-model="value" :id="uid" :disabled="disabled">
        <label class="form-check-label" :for="uid">[[ label ]]</label>
      </div>
      <input v-else type="text" class="form-control" v-model="value" :disabled="disabled">
    </div>
  `
});

const startApp = async () => {
  // Load all templates in parallel
  const [
    configTemplate,
    controlTemplate,
    statusTemplate,
    logTemplate,
    securityTemplate
  ] = await Promise.all([
    loadTemplate('config'),
    loadTemplate('control'),
    loadTemplate('status'),
    loadTemplate('log'),
    loadTemplate('security')
  ]);

  const app = createApp({
    data() {
      return {
        page: 'control',
        configPage: 'deviceDetails',
        isLoading: true,
        logContent: '',
        logTimer: null,
        baseImageUrl: '/latest.jpg',
        imageUrl: '/latest.jpg?' + Date.now(),
        stats: { latest: { loadAverage: [0, 0, 0] }, history: [] },
        config: {},
        schema: {},
        activeCameraTab: 'dawn',
        activeStreamTab: 'dawn',
        focusAidActive: false,
        isCapturing: false,
        captureStatusTimer: null,
        passwords: {
          current: '',
          new: '',
          confirm: ''
        },
        changePasswordMessage: '',
        changePasswordSuccess: false,
        isChangingPassword: false
        // Rimuoviamo i grafici da qui per renderli non reattivi
      };
    },
    computed: {
      currentPageComponent() {
        return this.isLoading ? null : `page-${this.page}`;
      }
    },
    created() {
      // Inizializziamo i grafici come proprietà non reattive dell'istanza
      this.tempChart = null;
      this.cpuChart = null;
    },
    mounted() {
      Promise.all([
        secureFetch('/api/config').then(r => r.json()),
        secureFetch('/api/schema').then(r => r.json())
      ]).then(([configData, schemaData]) => {
        this.config = configData;
        this.schema = schemaData;
        this.isLoading = false;
      }).catch(error => {
        if (error.message !== 'Session expired') {
          console.error("Failed to load initial data:", error);
        }
        this.isLoading = false;
      });

      if (this.page === 'control') {
        this.fetchCaptureStatus();
        this.captureStatusTimer = setInterval(this.fetchCaptureStatus, 2000);
      }
    },
    beforeUnmount() {
      clearInterval(this.imageInterval);
      clearInterval(this.captureStatusTimer);
      clearInterval(this.statsTimer);
    },
    methods: {
      async saveConfig() {
        await secureFetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(this.config) });
        alert('Configurazione salvata!');
      },
      async takePhoto() {
        try {
          const res = await secureFetch('/api/take_photo', { method: 'POST' });
          if (!res.ok) {
            alert('Impossibile scattare la foto.');
          }
        } catch (error) {
          if (error.message !== 'Session expired') {
            console.error('Errore durante lo scatto:', error);
            alert('Errore durante lo scatto. Controlla i log.');
          }
        }
      },
      async restartApp() {
        if (confirm('Sei sicuro di voler riavviare l\'applicazione?')) {
          try {
            await secureFetch('/api/restart', { method: 'POST' });
            alert('Riavvio in corso...');
          } catch (error) {
            if (error.message !== 'Session expired') {
              console.error('Errore durante il riavvio:', error);
              alert('Errore durante il riavvio. Controlla i log.');
            }
          }
        }
      },
      async startFocusAid() {
        const res = await secureFetch('/api/focus-aid/start', { method: 'POST' });
        if (res.ok) this.focusAidActive = true;
        else alert('Could not start focus aid.');
      },
      async stopFocusAid() {
        const res = await secureFetch('/api/focus-aid/stop', { method: 'POST' });
        if (res.ok) this.focusAidActive = false;
        else alert('Could not stop focus aid.');
      },
      fetchCaptureStatus() {
        // 1. Salva lo stato attuale PRIMA della chiamata API
        const wasCapturing = this.isCapturing;

        secureFetch('/api/status/capture')
          .then(res => res.json())
          .then(data => {
            this.isCapturing = data.is_capturing;

            // 2. Controlla se lo stato è appena cambiato da true a false
            if (wasCapturing && !this.isCapturing) {
              console.log("Cattura terminata. Aggiorno l'immagine.");
              // 3. Aggiorna l'URL con un timestamp per forzare il ricaricamento
              this.imageUrl = `${this.baseImageUrl}?_=${Date.now()}`;
            }
          })
          .catch(err => {
            if (err.message !== 'Session expired') {
              console.error("Errore recupero stato cattura:", err);
              this.isCapturing = false;
            }
          });
      },
      startLogPolling() {
        this.fetchLog();
        this.logTimer = setInterval(this.fetchLog, 2000);
      },
      stopLogPolling() {
        if (this.logTimer) { clearInterval(this.logTimer); this.logTimer = null; }
      },
      fetchLog() {
        secureFetch('/api/log').then(res => res.ok ? res.text() : Promise.reject('Errore')).then(text => {
          this.logContent = text;
          this.$nextTick(() => {
            const pre = document.getElementById('logView');
            if (pre) pre.scrollTop = pre.scrollHeight;
          });
        }).catch(err => {
          if (err.message !== 'Session expired') {
            this.logContent = `Errore caricamento log:\n${err}`;
          }
        });
      },
      fetchStats() {
        secureFetch('/api/stats').then(res => res.json()).then(data => {
          this.stats = data;
        }).catch(err => {
          if (err.message !== 'Session expired') {
            console.error("Errore recupero statistiche:", err);
          }
        });
      },
      updateCharts(history) {
        if (this.page !== 'status' || !history || !this.tempChart || !this.cpuChart) {
          return;
        }
        const labels = history.map(s => {
          if (s && typeof s.timestamp === 'number') {
            return new Date(s.timestamp * 1000).toLocaleTimeString();
          }
          return '';
        });
        const minTempData = history.map(s => s ? s.cpuTemperature.min : null);
        const avgTempData = history.map(s => s ? s.cpuTemperature.average : null);
        const maxTempData = history.map(s => s ? s.cpuTemperature.max : null);

        const minCpuData = history.map(s => s ? s.cpuUsage.min : null);
        const avgCpuData = history.map(s => s ? s.cpuUsage.average : null);
        const maxCpuData = history.map(s => s ? s.cpuUsage.max : null);


        this.tempChart.data.labels = labels;

        this.tempChart.data.datasets[0].data = minTempData;
        this.tempChart.data.datasets[1].data = avgTempData;
        this.tempChart.data.datasets[2].data = maxTempData;

        this.tempChart.update('none');

        this.cpuChart.data.labels = labels;
        this.cpuChart.data.datasets[0].data = minCpuData;
        this.cpuChart.data.datasets[1].data = avgCpuData;
        this.cpuChart.data.datasets[2].data = maxCpuData;
        this.cpuChart.update('none');
      },
      async logout() {
        try {
          const response = await fetch('/logout', { method: 'POST' });
          if (response.ok) {
            window.location.href = '/login';
          } else {
            console.error('Logout fallito');
            alert('Impossibile effettuare il logout.');
          }
        } catch (error) {
          console.error('Errore durante il logout:', error);
          alert('Errore di connessione durante il logout.');
        }
      },
      async changePassword(passwords) {
        if (passwords.new !== passwords.confirm) {
          this.changePasswordMessage = "Le nuove password non coincidono.";
          this.changePasswordSuccess = false;
          return;
        }
        if (!passwords.new || !passwords.current) {
          this.changePasswordMessage = "Tutti i campi sono obbligatori.";
          this.changePasswordSuccess = false;
          return;
        }

        this.isChangingPassword = true;
        this.changePasswordMessage = '';

        try {
          const response = await secureFetch('/api/change-password', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              current_password: passwords.current,
              new_password: passwords.new
            })
          });

          const result = await response.json();
          this.changePasswordMessage = result.message;
          this.changePasswordSuccess = response.ok;

          if (response.ok) {
            this.passwords.current = '';
            this.passwords.new = '';
            this.passwords.confirm = '';
          }
        } catch (error) {
          if (error.message !== 'Session expired') {
            this.changePasswordMessage = 'Errore di connessione con il server.';
            this.changePasswordSuccess = false;
          }
        } finally {
          this.isChangingPassword = false;
        }
      }
    },
    watch: {
      page(newVal, oldVal) {
        if (newVal === 'log') {
          this.startLogPolling();
        } else if (oldVal === 'log') {
          this.stopLogPolling();
        }

        if (newVal === 'status') {
          this.$nextTick(() => {
            this.tempGauge = Gauge(document.getElementById("tempGauge"), { min: 0, max: 85, label: val => val.toFixed(1) + " °C", value: 0 });
            this.cpuGauge = Gauge(document.getElementById("cpuGauge"), { min: 0, max: 100, label: val => val.toFixed(1) + " %", value: 0 });

            const chartOptions = {
              scales: {
                y: {
                  beginAtZero: true
                },
                x: {
                  ticks: {
                    maxRotation: 0,
                    minRotation: 0,
                    autoSkip: true,
                    maxTicksLimit: 10
                  }
                }
              },
              animation: false,
              elements: { point: { radius: 2 } }
            };

            tempDatasets = [
              { label: 'Min Temp °C', data: [] },
              { label: 'Avg Temp °C', data: [] },
              { label: 'Max Temp °C', data: [] }
            ]
            this.tempChart = new Chart(document.getElementById('tempChart'), { type: 'line', data: { labels: [], datasets: tempDatasets }, options: chartOptions });

            cpuDatasets = [
              { label: 'Min CPU Usage %', data: [] },
              { label: 'Avg CPU Usage %', data: [] },
              { label: 'Max CPU Usage %', data: [] }
            ]
            this.cpuChart = new Chart(document.getElementById('cpuChart'), { type: 'line', data: { labels: [], datasets: cpuDatasets }, options: chartOptions });

            this.fetchStats();
            this.statsTimer = setInterval(this.fetchStats, 1000);
          });
        } else if (oldVal === 'status') {
          clearInterval(this.statsTimer);
          this.statsTimer = null;
          if (this.tempChart) { this.tempChart.destroy(); this.tempChart = null; }
          if (this.cpuChart) { this.cpuChart.destroy(); this.cpuChart = null; }
        }

        if (newVal === 'control') {
          this.fetchCaptureStatus();
          this.captureStatusTimer = setInterval(this.fetchCaptureStatus, 2000);
        } else if (oldVal === 'control') {
          clearInterval(this.captureStatusTimer);
          this.captureStatusTimer = null;
        }
      },
      stats(newStats) {
        if (this.page === 'status') {
          if (newStats.latest) {
            const temp = parseFloat(newStats.latest.cpuTemperature);
            const usage = parseFloat(newStats.latest.cpuUsage);
            if (this.tempGauge && !isNaN(temp)) this.tempGauge.setValueAnimated(temp);
            if (this.cpuGauge && !isNaN(usage)) this.cpuGauge.setValueAnimated(usage);
          }
          if (newStats.history) {
            this.updateCharts(newStats.history);
          }
        }
      },
      'config.cameraParameters': {
        handler(newParams) {
          // Itera su tutte le fasi (dawn, day, dusk, night)
          for (const phase in newParams) {
            // Verifica che la proprietà appartenga all'oggetto stesso
            if (Object.prototype.hasOwnProperty.call(newParams, phase)) {
              const phaseParams = newParams[phase];

              // Se l'oggetto dei parametri esiste e AeEnable è true...
              if (phaseParams && phaseParams.AeEnable) {
                // ...forza i valori per il controllo manuale.
                phaseParams.AnalogueGain = 1.0;
                phaseParams.ExposureTime = 0;
              }
            }
          }
        },
        deep: true
      }
    }
  });

  // Registra i componenti delle pagine
  app.component('page-config', {
    props: ['config', 'schema', 'configPage', 'activeCameraTab', 'activeStreamTab'],
    template: configTemplate,
    components: { FieldRenderer }
  });
  app.component('page-control', {
    props: {
      imageUrl: { type: String, required: true },
      isCapturing: { type: Boolean, default: false },
      focusAidActive: { type: Boolean, default: false }
    },
    emits: ['take-photo', 'start-focus-aid', 'restart-app'],
    data() {
      return {
        rois: [],
        currentPoints: [],
        imageDimensions: { width: 0, height: 0 },
        fallbackImageUrl: 'placeholder.jpg',
        clickTimer: null // Per gestire la differenza tra clic e doppio clic
      };
    },
    mounted() {
      // Carica le ROI iniziali quando il componente è pronto
      this.loadPrivacyMask();
    },
    methods: {
      onImageError(event) {
        event.target.src = this.fallbackImageUrl;
      },
      onImageLoad(event) {
        const img = event.target;
        this.imageDimensions = {
          width: img.clientWidth,
          height: img.clientHeight,
        };
        // NUOVO: Ricarica/ridisegna le ROI con le dimensioni corrette
        this.loadPrivacyMask();
      },

      // --- LOGICA DI GESTIONE CLIC/DOPPIO CLIC CORRETTA ---
      handleSvgClick(event) {
        clearTimeout(this.clickTimer);
        this.clickTimer = setTimeout(() => {
          this.addPoint(event);
        }, 250);
      },

      completeCurrentRoi() {
        clearTimeout(this.clickTimer);

        if (this.currentPoints.length < 3) {
          this.currentPoints = [];
          console.warn("Disegno ROI annullato: servono almeno 3 punti.");
          return;
        }
        const newRoi = { id: Date.now(), points: this.currentPoints };
        this.rois.push(newRoi);
        this.currentPoints = [];
        this.savePrivacyMask();
      },

      // NUOVO: Annulla il disegno in corso con il tasto destro
      cancelCurrentRoi() {
        console.log("Disegno ROI in corso annullato.");
        this.currentPoints = [];
      },

      // Metodo separato per aggiungere un punto
      addPoint(event) {
        if (this.imageDimensions.width <= 0 || this.imageDimensions.height <= 0) {
          return;
        }
        const x_px = event.offsetX;
        const y_px = event.offsetY;
        const x_perc = (x_px / this.imageDimensions.width) * 100;
        const y_perc = (y_px / this.imageDimensions.height) * 100;
        this.currentPoints.push({ x: x_perc, y: y_perc });
      },
      // --- FINE LOGICA CLIC ---

      deleteRoi(roiId) {
        this.rois = this.rois.filter(roi => roi.id !== roiId);
        this.savePrivacyMask();
      },

      formatPoints(points) {
        return points.map(p => {
          const x_px = (p.x / 100) * this.imageDimensions.width;
          const y_px = (p.y / 100) * this.imageDimensions.height;
          return `${x_px},${y_px}`;
        }).join(' ');
      },

      getPointInPixels(point) {
        return {
          x: (point.x / 100) * this.imageDimensions.width,
          y: (point.y / 100) * this.imageDimensions.height
        };
      },
      getRoiCenter(roi) {
        const points = roi.points;
        if (!points || points.length === 0) return { x: 0, y: 0 };

        const sumX = points.reduce((sum, p) => sum + p.x, 0);
        const sumY = points.reduce((sum, p) => sum + p.y, 0);

        return {
          x: sumX / points.length,
          y: sumY / points.length
        };
      },

      async savePrivacyMask() {
        // ... (questo metodo rimane invariato)
        console.log("Saving privacy mask data:", this.rois);
        try {
          const response = await secureFetch('/api/save_privacy_mask', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(this.rois)
          });
          if (!response.ok) {
            console.error("Server error while saving privacy mask.");
          } else {
            console.log("Privacy mask saved successfully.");
          }
        } catch (error) {
          if (error.message !== 'Session expired') {
            console.error("Failed to save privacy mask:", error);
          }
        }
      },

      async loadPrivacyMask() {
        // ... (questo metodo rimane invariato)
        console.log("Loading initial privacy mask...");
        try {
          const response = await secureFetch('/api/privacy_mask');
          const data = await response.json();
          this.rois = data;
          console.log("Privacy mask loaded successfully:", this.rois);
        } catch (error) {
          if (error.message !== 'Session expired') {
            console.error("Failed to load privacy mask:", error);
          }
        }
      }
    },
    watch: {
      imageUrl() {
        this.imageDimensions = { width: 0, height: 0 };
      }
    },
    template: controlTemplate
  });
  app.component('page-status', {
    props: ['stats'],
    template: statusTemplate
  });
  app.component('page-log', {
    props: ['logContent'],
    template: logTemplate
  });
  app.component('page-security', {
    template: securityTemplate,
    props: ['passwords', 'isLoading', 'message', 'messageClass'],
    emits: ['change-password']
  });

  app.config.compilerOptions.delimiters = ['[[', ']]'];
  app.mount('#app');
};

startApp().catch(error => {
  // Gestisce l'errore di sessione scaduta che può avvenire durante il caricamento dei template
  if (error.message !== 'Session expired') {
    console.error("Failed to start the application:", error);
    document.body.innerHTML = '<div class="alert alert-danger">Impossibile avviare l\'applicazione. Controlla la console per i dettagli.</div>';
  }
});

