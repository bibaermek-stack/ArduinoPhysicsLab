(function (global) {
  "use strict";

  var MAX_POINTS = 300;
  var TEAL = "rgb(0,137,123)";
  var RECONNECT_MS = 1000;
  var COPY = {
    openApp: "Қолданбаны ашыңыз",
    connected: "Қосылған",
    measuring: "Өлшеу жүріп жатыр",
    offline: "Офлайн",
  };

  function statusEl() {
    return document.getElementById("live-status");
  }

  function chartEl() {
    return document.getElementById("live-chart");
  }

  function setStatus(text) {
    var el = statusEl();
    if (el) {
      el.textContent = text;
    }
  }

  function asNumber(value) {
    var n = Number(value);
    return typeof n === "number" && isFinite(n) ? n : null;
  }

  function drawChart(series) {
    var canvas = chartEl();
    if (!canvas || typeof canvas.getContext !== "function") {
      return;
    }
    var cssWidth = canvas.clientWidth || canvas.width || 0;
    var cssHeight = canvas.clientHeight || canvas.height || 0;
    if (cssWidth < 2) {
      cssWidth = 600;
    }
    if (cssHeight < 2) {
      cssHeight = 280;
    }
    var dpr = global.devicePixelRatio || 1;
    var pixelW = Math.max(1, Math.round(cssWidth * dpr));
    var pixelH = Math.max(1, Math.round(cssHeight * dpr));
    if (canvas.width !== pixelW) {
      canvas.width = pixelW;
    }
    if (canvas.height !== pixelH) {
      canvas.height = pixelH;
    }
    var ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cssWidth, cssHeight);

    var keys = Object.keys(series);
    var ymin = Infinity;
    var ymax = -Infinity;
    var k;
    var i;
    var pts;
    var v;
    for (k = 0; k < keys.length; k += 1) {
      pts = series[keys[k]];
      for (i = 0; i < pts.length; i += 1) {
        v = pts[i];
        if (v < ymin) {
          ymin = v;
        }
        if (v > ymax) {
          ymax = v;
        }
      }
    }
    if (!isFinite(ymin) || !isFinite(ymax)) {
      return;
    }
    if (ymin === ymax) {
      ymin -= 1;
      ymax += 1;
    }
    var pad = 12;
    var plotW = Math.max(1, cssWidth - pad * 2);
    var plotH = Math.max(1, cssHeight - pad * 2);
    var span = ymax - ymin;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.strokeStyle = TEAL;
    for (k = 0; k < keys.length; k += 1) {
      pts = series[keys[k]];
      if (!pts.length) {
        continue;
      }
      ctx.beginPath();
      var n = pts.length;
      var denom = Math.max(1, n - 1);
      for (i = 0; i < n; i += 1) {
        var x = pad + (i / denom) * plotW;
        var y = pad + (1 - (pts[i] - ymin) / span) * plotH;
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();
    }
  }

  function connect(opts) {
    opts = opts || {};
    var role = opts.role || "";
    var filterAccountId = null;
    var series = {};
    var timer = null;
    var closedForGood = false;

    function resetSeries() {
      series = {};
      drawChart(series);
    }

    function matchesFilter(accountId) {
      if (!filterAccountId) {
        return true;
      }
      return !accountId || accountId === filterAccountId;
    }

    function applyPresence(state) {
      if (state === "measuring") {
        setStatus(COPY.measuring);
      } else if (state === "idle") {
        setStatus(COPY.connected);
      } else if (state === "offline") {
        setStatus(role === "student" ? COPY.openApp : COPY.offline);
      } else {
        setStatus(COPY.openApp);
      }
    }

    function pushValues(values) {
      if (!values || typeof values !== "object") {
        return;
      }
      var key;
      var n;
      for (key in values) {
        if (!Object.prototype.hasOwnProperty.call(values, key)) {
          continue;
        }
        n = asNumber(values[key]);
        if (n === null) {
          continue;
        }
        if (!series[key]) {
          series[key] = [];
        }
        series[key].push(n);
        if (series[key].length > MAX_POINTS) {
          series[key].splice(0, series[key].length - MAX_POINTS);
        }
      }
    }

    function handleFrame(frame) {
      if (!frame || typeof frame !== "object") {
        return;
      }
      var type = frame.type;
      if (type === "hello") {
        setStatus(COPY.connected);
        return;
      }
      if (type === "presence") {
        if (!matchesFilter(frame.account_id)) {
          return;
        }
        applyPresence(frame.state);
        return;
      }
      if (type === "samples") {
        if (!matchesFilter(frame.account_id)) {
          return;
        }
        var points = frame.points;
        if (!points || !points.length) {
          return;
        }
        var p;
        for (p = 0; p < points.length; p += 1) {
          pushValues(points[p] && points[p].values);
        }
        setStatus(COPY.measuring);
        drawChart(series);
      }
    }

    function scheduleReconnect() {
      if (closedForGood || timer) {
        return;
      }
      timer = global.setTimeout(function () {
        timer = null;
        openSocket();
      }, RECONNECT_MS);
    }

    function openSocket() {
      if (closedForGood) {
        return;
      }
      var proto = location.protocol === "https:" ? "wss:" : "ws:";
      var url = proto + "//" + location.host + "/api/v1/live/ws";
      var ws;
      try {
        ws = new WebSocket(url);
      } catch (err) {
        scheduleReconnect();
        return;
      }
      ws.addEventListener("open", function () {
        setStatus(COPY.openApp);
      });
      ws.addEventListener("message", function (event) {
        var frame;
        try {
          frame = JSON.parse(event.data);
        } catch (parseErr) {
          return;
        }
        handleFrame(frame);
      });
      ws.addEventListener("close", function (event) {
        var code = event && event.code;
        if (code === 4401 || code === 4403) {
          closedForGood = true;
          setStatus(COPY.offline);
          return;
        }
        setStatus(COPY.openApp);
        scheduleReconnect();
      });
    }

    if (role === "teacher") {
      var buttons = document.querySelectorAll("[data-account-id]");
      var b;
      for (b = 0; b < buttons.length; b += 1) {
        buttons[b].addEventListener("click", function (ev) {
          filterAccountId = ev.currentTarget.getAttribute("data-account-id");
          resetSeries();
        });
      }
      if (buttons.length) {
        filterAccountId = buttons[0].getAttribute("data-account-id");
      }
    }

    if (global.addEventListener) {
      global.addEventListener("resize", function () {
        drawChart(series);
      });
    }

    setStatus(COPY.openApp);
    openSocket();
  }

  global.LiveLab = { connect: connect };
})(window);
