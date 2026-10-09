/* Map same-origin root API calls through the reverse-proxy mount.
 * Non-API and absolute remote URLs remain untouched.
 */
(() => {
  const nativeFetch = window.fetch.bind(window);
  const scope = input => typeof input === "string" && input.startsWith("/api/") && !input.startsWith("//")
    ? new URL(input.slice(1), document.baseURI).toString()
    : input;
  window.fetch = (input, options) => nativeFetch(scope(input), options);
})();
