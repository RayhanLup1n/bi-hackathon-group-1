/* Runtime configuration for RADAR Pangan. */
(function () {
  window.RADAR_API_BASE_URL = window.RADAR_API_BASE_URL || "";
  var apiBase = window.RADAR_API_BASE_URL.replace(/\/+$/, "");
  window.RADAR_CONFIG = Object.freeze({ apiBaseUrl: apiBase });

  if (!apiBase || window.__radarFetchPatched) return;

  var nativeFetch = window.fetch.bind(window);
  window.fetch = function radarFetch(input, init) {
    var requestUrl = typeof input === "string" ? input : input.url;
    if (!requestUrl.startsWith("/api/") && requestUrl !== "/health") {
      return nativeFetch(input, init);
    }
    var targetUrl = apiBase + requestUrl;
    return typeof input === "string"
      ? nativeFetch(targetUrl, init)
      : nativeFetch(new Request(targetUrl, input), init);
  };
  window.__radarFetchPatched = true;
})();
