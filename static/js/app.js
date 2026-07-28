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
    options() { return this.schema?.[this.keyName]?.options || []; },
    // Liste di stringhe (es. destinazioni RTMP): una per riga nel textarea
    listText: {
      get() { return Array.isArray(this.value) ? this.value.join('\n') : (this.value || ''); },
      set(v) { this.value = v.split('\n').map(s => s.trim()).filter(s => s.length > 0); }
    }
  },
  // 2. Applica la prop agli elementi del template
  template: `
    <div class="mb-3">
      <select v-if="fieldType === 'select'" v-model="value" class="form-select" :disabled="disabled">
        <option v-for="(opt, index) in options" :value="index">[[ opt ]]</option>
      </select>
      <textarea v-else-if="fieldType === 'textlist'" class="form-control" rows="3" v-model="listText" :disabled="disabled"></textarea>
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
    systemTemplate,
    licenseTemplate,
    timelapseTemplate
  ] = await Promise.all([
    loadTemplate('config'),
    loadTemplate('control'),
    loadTemplate('status'),
    loadTemplate('log'),
    loadTemplate('system'),
    loadTemplate('license'),
    loadTemplate('timelapse')
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
        captureElapsed: 0,
        captureStatusTimer: null,
        streamRunning: false,
        livePreview: false,
        previewUrl: '',
        previewTimer: null,
        passwords: {
          current: '',
          new: '',
          confirm: ''
        },
        changePasswordMessage: '',
        changePasswordSuccess: false,
        isChangingPassword: false,
        timelapseStats: null,
        timelapseRunning: false
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
      // Esito noto prima di avviare un montaggio: serve solo a capire quando
      // ne compare uno nuovo, non deve essere reattivo.
      this.timelapseStartedAt = null;
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
        this.pollControlStatus();
        this.captureStatusTimer = setInterval(this.pollControlStatus, 2000);
      }
    },
    beforeUnmount() {
      clearInterval(this.imageInterval);
      clearInterval(this.captureStatusTimer);
      clearInterval(this.previewTimer);
      clearInterval(this.statsTimer);
      clearInterval(this.timelapseTimer);
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
      async loadTimelapseStats() {
        try {
          const res = await secureFetch('/api/timelapse');
          this.timelapseStats = await res.json();
          // Il montaggio prosegue in background: finche' non compare un esito
          // piu' recente si continua a mostrare lo stato "in corso".
          if (this.timelapseRunning && this.timelapseStats.last_result) {
            if (this.timelapseStats.last_result.at !== this.timelapseStartedAt) {
              this.timelapseRunning = false;
            }
          }
        } catch (error) {
          if (error.message !== 'Session expired') {
            console.error('Errore nel leggere lo stato del timelapse:', error);
          }
        }
      },
      async runTimelapse(upload) {
        const question = upload
          ? 'Montare e pubblicare subito il timelapse su YouTube?'
          : 'Montare subito il timelapse senza pubblicarlo?';
        if (!confirm(question)) return;
        try {
          this.timelapseStartedAt = this.timelapseStats?.last_result?.at || null;
          const res = await secureFetch('/api/timelapse/run', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ upload: upload })
          });
          if (res.ok) {
            this.timelapseRunning = true;
          } else {
            alert('Impossibile avviare il montaggio.');
          }
        } catch (error) {
          if (error.message !== 'Session expired') {
            console.error('Errore avviando il timelapse:', error);
            alert('Errore avviando il timelapse. Controlla i log.');
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
            this.captureElapsed = data.elapsed || 0;

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
      pollControlStatus() {
        this.fetchCaptureStatus();
        this.fetchStreamStatus();
      },
      fetchStreamStatus() {
        secureFetch('/api/status/stream')
          .then(res => res.json())
          .then(data => {
            this.streamRunning = !!data.running;
            // Lo streaming si ferma a ogni scatto: senza fotogrammi freschi
            // si torna all'ultima immagine invece di mostrarne uno vecchio.
            if (!this.streamRunning && this.livePreview) this.setLivePreview(false);
          })
          .catch(err => {
            if (err.message !== 'Session expired') {
              console.error('Errore recupero stato streaming:', err);
              this.streamRunning = false;
            }
          });
      },
      setLivePreview(active) {
        this.livePreview = !!active;
        clearInterval(this.previewTimer);
        this.previewTimer = null;
        if (this.livePreview) {
          this.refreshPreview();
          this.previewTimer = setInterval(this.refreshPreview, 1000);
        }
      },
      refreshPreview() {
        this.previewUrl = `/stream_latest.jpg?_=${Date.now()}`;
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

        if (newVal === 'timelapse') {
          this.loadTimelapseStats();
          this.timelapseTimer = setInterval(this.loadTimelapseStats, 5000);
        } else if (oldVal === 'timelapse') {
          clearInterval(this.timelapseTimer);
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
          this.pollControlStatus();
          this.captureStatusTimer = setInterval(this.pollControlStatus, 2000);
        } else if (oldVal === 'control') {
          clearInterval(this.captureStatusTimer);
          this.captureStatusTimer = null;
          // L'anteprima non serve fuori dalla pagina: si spegne il timer
          this.setLivePreview(false);
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
    data() {
      return {
        youtubeAuth: { active: false, userCode: '', verificationUrl: '', message: '', ok: false },
        assets: [],
        assetCategories: {},
        assetFilter: '',
        assetUpload: { category: 'audio', busy: false, message: '', ok: false }
      };
    },
    created() {
      // Timer e stato di controllo non reattivi
      this.youtubeAuthTimer = null;
      this.youtubeAuthExpiry = 0;
      this.youtubeAuthPolling = false;
      // Servono anche fuori dalla pagina Assets: le tendine dell'audio e
      // dei loghi si popolano da qui.
      this.loadAssets();
    },
    computed: {
      audioAssets() {
        return this.assets.filter(item => item.category === 'audio');
      },
      logoAssets() {
        return this.assets.filter(item => item.category === 'logo');
      },
      filteredAssets() {
        if (!this.assetFilter) return this.assets;
        return this.assets.filter(item => item.category === this.assetFilter);
      }
    },
    beforeUnmount() {
      this.stopYoutubeAuth();
    },
    methods: {
      async loadAssets() {
        try {
          const res = await secureFetch('/api/assets');
          const data = await res.json();
          if (data.success) {
            this.assets = data.assets || [];
            this.assetCategories = data.categories || {};
          }
        } catch (error) {
          if (error.message !== 'Session expired') this.assets = [];
        }
      },
      async uploadAsset() {
        const input = this.$refs.assetFile;
        if (!input || !input.files || !input.files.length) {
          this.assetUpload.message = 'Scegli prima un file.';
          this.assetUpload.ok = false;
          return;
        }
        const body = new FormData();
        body.append('file', input.files[0]);
        body.append('category', this.assetUpload.category);

        this.assetUpload.busy = true;
        try {
          // Niente Content-Type: lo mette il browser, con il boundary
          const res = await secureFetch('/api/assets', { method: 'POST', body });
          const data = await res.json();
          this.assetUpload.ok = !!data.success;
          this.assetUpload.message = data.success
            ? 'Caricato ' + data.asset.name + '.'
            : (data.error || 'Caricamento non riuscito.');
          if (data.success) {
            input.value = '';
            await this.loadAssets();
          }
        } catch (error) {
          if (error.message !== 'Session expired') {
            this.assetUpload.ok = false;
            this.assetUpload.message = 'Errore di rete durante il caricamento.';
          }
        } finally {
          this.assetUpload.busy = false;
        }
      },
      async deleteAsset(item) {
        if (!confirm('Eliminare ' + item.name + '?')) return;
        try {
          const res = await secureFetch('/api/assets/' + item.category + '/' + encodeURIComponent(item.name),
            { method: 'DELETE' });
          const data = await res.json();
          this.assetUpload.ok = !!data.success;
          this.assetUpload.message = data.success
            ? 'Eliminato ' + item.name + '.'
            : (data.error || 'Eliminazione non riuscita.');
          if (data.success) await this.loadAssets();
        } catch (error) {
          if (error.message !== 'Session expired') {
            this.assetUpload.ok = false;
            this.assetUpload.message = 'Errore di rete durante l\'eliminazione.';
          }
        }
      },
      missingAsset(value) {
        // Un asset cancellato lascia il riferimento in configurazione: senza
        // questa voce la tendina sembrerebbe semplicemente vuota.
        if (!value) return false;
        return !this.assets.some(item => item.reference === value);
      },
      assetReference(value) {
        // Vuoto per gli URL http: la tendina resta su "Scegli fra gli assets"
        return (value || '').startsWith('asset:') ? value : '';
      },
      assetUrl(value) {
        const reference = this.assetReference(value);
        if (!reference) return '';
        return '/assets/' + reference.slice('asset:'.length);
      },
      formatSize(bytes) {
        if (bytes >= 1048576) return (bytes / 1048576).toFixed(1) + ' MB';
        if (bytes >= 1024) return Math.round(bytes / 1024) + ' kB';
        return bytes + ' B';
      },
      async startYoutubeAuth() {
        const yl = this.config.youtubeLive || {};
        if (!yl.client_id || !yl.client_secret) {
          this.youtubeAuth.message = 'Inserisci prima Client ID e Client Secret.';
          this.youtubeAuth.ok = false;
          return;
        }
        this.stopYoutubeAuth();
        this.youtubeAuth = { active: true, userCode: '', verificationUrl: '', message: '', ok: false };
        try {
          const res = await secureFetch('/api/youtube/device/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ client_id: yl.client_id, client_secret: yl.client_secret })
          });
          const data = await res.json();
          if (!data.success) {
            this.youtubeAuth.active = false;
            this.youtubeAuth.message = data.error || 'Avvio autenticazione fallito.';
            this.youtubeAuth.ok = false;
            return;
          }
          this.youtubeAuth.userCode = data.user_code;
          this.youtubeAuth.verificationUrl = data.verification_url;
          this.youtubeAuthExpiry = Date.now() + (data.expires_in || 1800) * 1000;
          const interval = Math.max(3, data.interval || 5);
          this.youtubeAuthTimer = setInterval(this.pollYoutubeAuth, interval * 1000);
        } catch (error) {
          this.youtubeAuth.active = false;
          if (error.message !== 'Session expired') {
            this.youtubeAuth.message = 'Errore di rete durante l\'avvio.';
            this.youtubeAuth.ok = false;
          }
        }
      },
      async pollYoutubeAuth() {
        if (this.youtubeAuthPolling) return; // evita richieste sovrapposte
        if (Date.now() > this.youtubeAuthExpiry) {
          this.stopYoutubeAuth();
          this.youtubeAuth.message = 'Codice scaduto, riprova.';
          this.youtubeAuth.ok = false;
          return;
        }
        this.youtubeAuthPolling = true;
        try {
          const res = await secureFetch('/api/youtube/device/poll', { method: 'POST' });
          const data = await res.json();
          if (data.status === 'authorized') {
            this.config.youtubeLive.refresh_token = data.refresh_token;
            this.stopYoutubeAuth();
            // Il canale autorizzato va mostrato: se non è quello della stream
            // key la diretta fallisce con un 403 solo allo scatto successivo.
            this.youtubeAuth.message = data.channel
              ? 'Autenticato sul canale "' + data.channel + '". Verifica che sia quello della stream key, poi salva la configurazione.'
              : 'Autenticazione completata. Ricordati di salvare la configurazione.';
            this.youtubeAuth.ok = true;
          } else if (data.status !== 'pending') {
            this.stopYoutubeAuth();
            this.youtubeAuth.message = 'Autenticazione non riuscita: ' + (data.error || data.status);
            this.youtubeAuth.ok = false;
          }
        } catch (error) {
          if (error.message === 'Session expired') this.stopYoutubeAuth();
          // un errore singolo di rete non interrompe l'attesa
        } finally {
          this.youtubeAuthPolling = false;
        }
      },
      stopYoutubeAuth() {
        clearInterval(this.youtubeAuthTimer);
        this.youtubeAuthTimer = null;
        this.youtubeAuth.active = false;
        this.youtubeAuth.userCode = '';
      }
    },
    template: configTemplate,
    components: { FieldRenderer }
  });
  app.component('page-control', {
    props: {
      imageUrl: { type: String, required: true },
      previewUrl: { type: String, default: '' },
      streamRunning: { type: Boolean, default: false },
      livePreview: { type: Boolean, default: false },
      isCapturing: { type: Boolean, default: false },
      captureElapsed: { type: Number, default: 0 },
      focusAidActive: { type: Boolean, default: false }
    },
    emits: ['take-photo', 'start-focus-aid', 'restart-app', 'toggle-live-preview'],
    computed: {
      displayedImageUrl() {
        return this.livePreview && this.previewUrl ? this.previewUrl : this.imageUrl;
      },
      captureElapsedLabel() {
        // Di notte la cattura dura minuti: il tempo trascorso dice che sta
        // ancora lavorando invece di lasciar pensare a un blocco.
        const s = this.captureElapsed;
        if (!s) return '';
        return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`;
      }
    },
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
        // Sull'anteprima in diretta le ROI non si disegnano: l'inquadratura
        // dello streaming non coincide con quella dello scatto.
        if (this.livePreview) return;
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
        const newRoi = { id: Date.now(), points: this.currentPoints, mode: 'blur' };
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

      // Sfocatura o copertura completa dell'area
      setRoiMode(roi, mode) {
        roi.mode = mode;
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
  app.component('page-system', {
    template: systemTemplate,
    props: ['passwords', 'isLoading', 'message', 'messageClass'],
    emits: ['change-password'],
    data() {
      return {
        backupPassphrase: '',
        backupBusy: false,
        backupMessage: '',
        backupSuccess: false,
        restoreFile: null,
        restorePassphrase: '',
        restoreBusy: false
      };
    },
    methods: {
      setBackupMessage(text, success) {
        this.backupMessage = text;
        this.backupSuccess = success;
      },
      async downloadBackup() {
        this.backupBusy = true;
        this.setBackupMessage('', false);
        try {
          const response = await secureFetch('/api/config/backup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ passphrase: this.backupPassphrase })
          });
          if (!response.ok) {
            const result = await response.json().catch(() => ({}));
            this.setBackupMessage(result.message || 'Backup non riuscito.', false);
            return;
          }

          // Il file arriva come blob: lo si salva senza lasciare la pagina.
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = (response.headers.get('Content-Disposition') || '')
            .split('filename=')[1] || 'zerocam-backup.json';
          document.body.appendChild(link);
          link.click();
          link.remove();
          URL.revokeObjectURL(url);

          this.backupPassphrase = '';
          this.setBackupMessage('Backup scaricato. Conserva la passphrase: senza non è recuperabile.', true);
        } catch (error) {
          if (error.message !== 'Session expired') {
            this.setBackupMessage('Errore di connessione durante il backup.', false);
          }
        } finally {
          this.backupBusy = false;
        }
      },
      pickBackupFile(event) {
        this.restoreFile = event.target.files[0] || null;
      },
      async uploadRestore() {
        if (!this.restoreFile) return;
        if (!confirm('La configurazione attuale verrà sovrascritta. Procedere?')) return;

        this.restoreBusy = true;
        this.setBackupMessage('', false);
        try {
          let backup;
          try {
            backup = JSON.parse(await this.restoreFile.text());
          } catch (e) {
            this.setBackupMessage('Il file selezionato non è un JSON valido.', false);
            return;
          }

          const response = await secureFetch('/api/config/restore', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ backup: backup, passphrase: this.restorePassphrase })
          });
          const result = await response.json().catch(() => ({}));
          this.setBackupMessage(result.message || 'Ripristino non riuscito.', response.ok);

          if (response.ok) {
            this.restorePassphrase = '';
            this.restoreFile = null;
            // Ricarica per mostrare la configurazione appena ripristinata.
            setTimeout(() => window.location.reload(), 2000);
          }
        } catch (error) {
          if (error.message !== 'Session expired') {
            this.setBackupMessage('Errore di connessione durante il ripristino.', false);
          }
        } finally {
          this.restoreBusy = false;
        }
      }
    }
  });
  app.component('page-license', {
    template: licenseTemplate
  });
  app.component('page-timelapse', {
    props: ['config', 'schema', 'timelapseStats', 'timelapseRunning'],
    emits: ['run-timelapse', 'refresh-timelapse'],
    data() {
      return {
        galleryDays: [],
        galleryDay: null,
        galleryFrames: [],
        galleryIndex: 0,
        galleryPlaying: false,
        gallerySpeed: 5
      };
    },
    computed: {
      galleryFrameUrl() {
        const name = this.galleryFrames[this.galleryIndex];
        return name ? `/timelapse/frame/${name}` : '';
      },
      galleryFrameLabel() {
        const name = this.galleryFrames[this.galleryIndex];
        if (!name) return '';
        // Nome nel formato YYYYMMDD-HHMMSS.jpg
        const t = name.slice(9, 15);
        return `${t.slice(0, 2)}:${t.slice(2, 4)}:${t.slice(4, 6)}`;
      }
    },
    created() {
      // Timer e cache dei fotogrammi: non reattivi, come per i grafici
      this.galleryTimer = null;
      this.galleryPreload = new Map();
    },
    mounted() {
      this.loadGalleryDays();
    },
    beforeUnmount() {
      this.stopGalleryPlay();
    },
    watch: {
      gallerySpeed() {
        // Cambiare velocita' durante la riproduzione riavvia il timer
        if (this.galleryPlaying) {
          this.stopGalleryPlay();
          this.startGalleryPlay();
        }
      }
    },
    methods: {
      async loadGalleryDays() {
        try {
          const res = await secureFetch('/api/timelapse/frames');
          const data = await res.json();
          this.galleryDays = data.days || [];
          if (this.galleryDays.length > 0) {
            const stillThere = this.galleryDays.some(d => d.day === this.galleryDay);
            await this.selectGalleryDay(stillThere ? this.galleryDay : this.galleryDays[0].day);
          } else {
            this.galleryFrames = [];
          }
        } catch (error) {
          if (error.message !== 'Session expired') {
            console.error('Errore nel caricare i giorni della galleria:', error);
          }
        }
      },
      async selectGalleryDay(day) {
        this.stopGalleryPlay();
        try {
          const res = await secureFetch('/api/timelapse/frames?day=' + encodeURIComponent(day));
          const data = await res.json();
          this.galleryDay = day;
          this.galleryFrames = data.frames || [];
          this.galleryIndex = 0;
          // Cambiando giorno le promesse del giorno precedente non servono piu'
          this.galleryPreload.clear();
        } catch (error) {
          if (error.message !== 'Session expired') {
            console.error('Errore nel caricare i fotogrammi:', error);
          }
        }
      },
      stepGallery(delta) {
        this.stopGalleryPlay();
        const last = this.galleryFrames.length - 1;
        this.galleryIndex = Math.min(last, Math.max(0, this.galleryIndex + delta));
      },
      toggleGalleryPlay() {
        if (this.galleryPlaying) {
          this.stopGalleryPlay();
        } else {
          this.startGalleryPlay();
        }
      },
      startGalleryPlay() {
        if (this.galleryFrames.length < 2) return;
        // Riparte dall'inizio se siamo gia' in fondo
        if (this.galleryIndex >= this.galleryFrames.length - 1) this.galleryIndex = 0;
        this.galleryPlaying = true;
        this.playGalleryFrame();
      },
      playGalleryFrame() {
        // L'indice avanza solo quando il fotogramma successivo e' gia' in
        // cache: con un intervallo fisso le richieste si accodavano piu' in
        // fretta di quanto il dispositivo le servisse e l'immagine restava
        // ferma sull'ultima scaricata, mentre cursore ed etichetta correvano.
        const next = this.galleryIndex + 1;
        if (next > this.galleryFrames.length - 1) {
          this.stopGalleryPlay();
          return;
        }

        const startedAt = Date.now();
        this.preloadGalleryFrame(next).then(() => {
          if (!this.galleryPlaying) return;
          this.galleryIndex = next;
          // Tiene un fotogramma di vantaggio, cosi' il prossimo scatto e' pronto
          this.preloadGalleryFrame(next + 1);
          const wait = Math.max(0, (1000 / this.gallerySpeed) - (Date.now() - startedAt));
          this.galleryTimer = setTimeout(this.playGalleryFrame, wait);
        });
      },
      preloadGalleryFrame(index) {
        const name = this.galleryFrames[index];
        if (!name) return Promise.resolve();
        // Il fotogramma gia' richiesto non viene riscaricato: la stessa
        // promessa serve sia al prefetch sia all'attesa prima di mostrarlo.
        if (this.galleryPreload.has(name)) return this.galleryPreload.get(name);

        const pending = new Promise(resolve => {
          const img = new Image();
          // Anche un fotogramma illeggibile deve lasciar proseguire la riproduzione
          img.onload = img.onerror = resolve;
          img.src = `/timelapse/frame/${name}`;
        });
        this.galleryPreload.set(name, pending);
        return pending;
      },
      stopGalleryPlay() {
        clearTimeout(this.galleryTimer);
        this.galleryPlaying = false;
      },
      formatBytes(bytes) {
        if (!bytes) return '0 B';
        const units = ['B', 'kB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1) + ' ' + units[i];
      }
    },
    components: { FieldRenderer },
    template: timelapseTemplate
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

