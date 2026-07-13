/* Runtime configuration for Cloudflare Pages and same-origin hosting. */
(function () {
  window.RADAR_API_BASE_URL = window.RADAR_API_BASE_URL || "";
  const apiBase = window.RADAR_API_BASE_URL.replace(/\/+$/, "");
  window.RADAR_CONFIG = Object.freeze({ apiBaseUrl: apiBase });

  if (!apiBase || window.__radarFetchPatched) return;

  const nativeFetch = window.fetch.bind(window);
  window.fetch = function radarFetch(input, init) {
    const requestUrl = typeof input === "string" ? input : input.url;
    if (!requestUrl.startsWith("/api/") && requestUrl !== "/health") {
      return nativeFetch(input, init);
    }
    const targetUrl = apiBase + requestUrl;
    return typeof input === "string"
      ? nativeFetch(targetUrl, init)
      : nativeFetch(new Request(targetUrl, input), init);
  };
  window.__radarFetchPatched = true;
})();
