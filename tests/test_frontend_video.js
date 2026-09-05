"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class FakeClassList {
  constructor() { this.values = new Set(); }
  add(...names) { names.forEach(name => this.values.add(name)); }
  remove(...names) { names.forEach(name => this.values.delete(name)); }
  contains(name) { return this.values.has(name); }
  toggle(name, force) {
    const enabled = force === undefined ? !this.contains(name) : !!force;
    if (enabled) this.add(name); else this.remove(name);
    return enabled;
  }
}

class FakeElement {
  constructor() {
    this.classList = new FakeClassList();
    this.dataset = {};
    this.style = {};
    this.value = "";
    this.disabled = false;
    this.parentElement = null;
    this.isConnected = true;
    this.listeners = new Map();
    this.queries = new Map();
    this._textContent = "";
    this._innerHTML = "";
  }
  set textContent(value) {
    this._textContent = String(value);
    this._innerHTML = this._textContent
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }
  get textContent() { return this._textContent; }
  set innerHTML(value) { this._innerHTML = String(value); }
  get innerHTML() { return this._innerHTML; }
  addEventListener(name, fn) { this.listeners.set(name, fn); }
  querySelector(selector) { return this.queries.get(selector) || null; }
  scrollIntoView() {}
  removeAttribute(name) {
    if (name === "src") this.src = "";
  }
}

class FakeVideo extends FakeElement {
  constructor(nativeHls) {
    super();
    this.nativeHls = nativeHls;
    this.src = "";
    this.pauseCalls = 0;
    this.loadCalls = 0;
  }
  canPlayType(type) {
    return type === "application/vnd.apple.mpegurl" && this.nativeHls ? "maybe" : "";
  }
  pause() { this.pauseCalls += 1; }
  load() { this.loadCalls += 1; }
}

class FakeHls {
  static Events = {
    ERROR: "error",
    MANIFEST_PARSED: "manifestParsed",
  };
  static instances = [];
  static isSupported() { return true; }

  constructor(options) {
    this.options = options;
    this.handlers = new Map();
    this.destroyCalls = 0;
    FakeHls.instances.push(this);
  }
  attachMedia(video) { this.video = video; }
  loadSource(url) { this.source = url; }
  on(name, fn) { this.handlers.set(name, fn); }
  destroy() { this.destroyCalls += 1; }
}

function response(body, status = 200) {
  return { status, json: async () => body };
}

function deferred() {
  let resolve;
  const promise = new Promise(done => { resolve = done; });
  return { promise, resolve };
}

async function flush() {
  await new Promise(resolve => setImmediate(resolve));
  await new Promise(resolve => setImmediate(resolve));
}

function defaultResponse(url) {
  if (url === "/api/stats") {
    return response({
      status: "idle", meta_busy: false, posts: 0, images: 0, deleted: 0,
      disk_usage: 0, progress: {}, log: [],
    });
  }
  if (url === "/api/tags") return response({ tags: [] });
  if (url === "/api/categories") return response({ categories: [] });
  if (url === "/api/cosers") return response({ cosers: [] });
  if (url.startsWith("/api/posts?")) return response({ total: 0, items: [] });
  throw new Error(`Unexpected startup fetch: ${url}`);
}

async function loadApp(storedToken = "") {
  const htmlPath = path.join(__dirname, "..", "static", "index.html");
  const html = fs.readFileSync(htmlPath, "utf8");
  const scripts = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/g)];
  const source = scripts.at(-1)[1];
  const elements = new Map();
  const getElement = id => {
    if (!elements.has(id)) elements.set(id, new FakeElement());
    return elements.get(id);
  };
  getElement("inpSearch").value = "";
  getElement("inpUrl").value = "https://cosplaytele.com";
  getElement("inpProxy").value = "";
  getElement("inpStart").value = "1";
  getElement("inpEnd").value = "";

  const context = vm.createContext({
    URL,
    Hls: FakeHls,
    clearInterval() {},
    clearTimeout() {},
    confirm: () => true,
    console,
    document: {
      body: new FakeElement(),
      createElement: () => new FakeElement(),
      getElementById: getElement,
      addEventListener() {},
    },
    fetch: async (url, options) => defaultResponse(url, options),
    location: {
      href: "http://gallery.test/",
      origin: "http://gallery.test",
      reload() {},
    },
    localStorage: {
      getItem: () => storedToken,
      setItem() {},
    },
    setInterval: () => 1,
    setTimeout: () => 1,
  });
  vm.runInContext(source, context, { filename: htmlPath });
  await flush();
  return { context, elements, html };
}

function createVideoItem(nativeHls = false) {
  const item = new FakeElement();
  const button = new FakeElement();
  const frame = new FakeElement();
  const video = new FakeVideo(nativeHls);
  const status = new FakeElement();
  const message = new FakeElement();
  const retry = new FakeElement();

  button.parentElement = item;
  frame.parentElement = item;
  status.parentElement = frame;
  retry.parentElement = status;
  item.queries.set(".vframe", frame);
  item.queries.set(".vexpand", button);
  frame.queries.set("video", video);
  frame.queries.set(".vstatus", status);
  status.queries.set(".vmessage", message);
  status.queries.set(".vretry", retry);
  return { item, button, frame, video, status, message, retry };
}

function setCurrentPost(context, slug) {
  context.testSlug = slug;
  vm.runInContext("curPost = { slug: testSlug }", context);
}

async function toggle(context, button) {
  context.testButton = button;
  return vm.runInContext("toggleVideo(testButton)", context);
}

async function retry(context, button) {
  context.testRetryButton = button;
  return vm.runInContext("retryVideo(testRetryButton)", context);
}

test.beforeEach(() => { FakeHls.instances = []; });

test("a collapsed player ignores a late playback response", async () => {
  const { context } = await loadApp("secret");
  const request = deferred();
  context.fetch = () => request.promise;
  setCurrentPost(context, "article");
  const ui = createVideoItem();
  ui.button.dataset.index = "0";

  const pending = toggle(context, ui.button);
  await flush();
  await toggle(context, ui.button);
  request.resolve(response({ url: "/video/session/master.m3u8", type: "hls" }));
  await pending;

  assert.equal(ui.frame.classList.contains("open"), false);
  assert.equal(ui.button.textContent, "在线观看");
  assert.equal(ui.video.src, "");
  assert.equal(FakeHls.instances.length, 0);
});

test("collapsing an initialized hls.js player destroys it and clears the video", async () => {
  const { context } = await loadApp("secret");
  context.fetch = async () => response({ url: "/video/session/master.m3u8", type: "hls" });
  setCurrentPost(context, "article");
  const ui = createVideoItem();
  ui.button.dataset.index = "0";

  await toggle(context, ui.button);
  const player = FakeHls.instances[0];
  assert.ok(player);

  await toggle(context, ui.button);

  assert.equal(player.destroyCalls, 1);
  assert.equal(ui.video.src, "");
  assert.equal(ui.video.pauseCalls, 1);
  assert.equal(ui.video.loadCalls, 1);
});

test("native HLS receives the token in its same-origin URL", async () => {
  const { context } = await loadApp("a token&value");
  context.Hls = class extends FakeHls { static isSupported() { return false; } };
  const requests = [];
  context.fetch = async (url, options) => {
    requests.push({ url, options });
    return response({ url: "/video/session/master.m3u8?quality=auto", type: "hls" });
  };
  setCurrentPost(context, "part 2/特");
  const ui = createVideoItem(true);
  ui.button.dataset.index = "3";

  await toggle(context, ui.button);

  assert.equal(requests[0].url, "/api/videos/part%202%2F%E7%89%B9/3");
  assert.equal(requests[0].options.headers["X-Access-Token"], "a token&value");
  assert.equal(
    ui.video.src,
    "/video/session/master.m3u8?quality=auto&token=a+token%26value",
  );
  assert.equal(FakeHls.instances.length, 0);
});

test("MSE-capable browsers use hls.js even when native HLS is advertised", async () => {
  const { context } = await loadApp();
  context.fetch = async () => response({url:"/video/session/master",type:"hls"});
  setCurrentPost(context, "article");
  const ui = createVideoItem(true);
  ui.button.dataset.index = "0";
  await toggle(context, ui.button);
  assert.equal(FakeHls.instances.length, 1);
  assert.equal(ui.video.src, "");
});

test("hls.js adds the token header only to same-origin media requests", async () => {
  const { context } = await loadApp("secret");
  context.fetch = async () => response({ url: "/video/session/master.m3u8", type: "hls" });
  setCurrentPost(context, "article");
  const ui = createVideoItem();
  ui.button.dataset.index = "0";

  await toggle(context, ui.button);
  const player = FakeHls.instances[0];
  const sameOriginHeaders = {};
  const externalHeaders = {};
  player.options.xhrSetup({
    setRequestHeader(name, value) { sameOriginHeaders[name] = value; },
  }, "http://gallery.test/video/session/segment.png");
  player.options.xhrSetup({
    setRequestHeader(name, value) { externalHeaders[name] = value; },
  }, "https://media.example/segment.ts");

  assert.equal(player.source, "/video/session/master.m3u8?token=secret");
  assert.deepEqual(sameOriginHeaders, { "X-Access-Token": "secret" });
  assert.deepEqual(externalHeaders, {});
});

test("a failed playback request stays open and can be retried", async () => {
  const { context } = await loadApp("secret");
  let attempt = 0;
  context.fetch = async () => {
    attempt += 1;
    if (attempt === 1) return response({ error: "upstream unavailable" }, 502);
    return response({ url: "/video/new/master.m3u8", type: "hls" });
  };
  setCurrentPost(context, "article");
  const ui = createVideoItem();
  ui.button.dataset.index = "0";

  await toggle(context, ui.button);

  assert.equal(ui.frame.classList.contains("open"), true);
  assert.equal(ui.message.textContent, "视频加载失败：upstream unavailable");
  assert.equal(ui.retry.style.display, "inline-flex");

  await retry(context, ui.retry);

  assert.equal(attempt, 2);
  assert.equal(FakeHls.instances.length, 1);
  assert.equal(ui.button.textContent, "收起");
});

test("a fatal hls.js media error destroys the player and offers retry", async () => {
  const { context } = await loadApp("secret");
  context.fetch = async () => response({ url: "/video/session/master.m3u8", type: "hls" });
  setCurrentPost(context, "article");
  const ui = createVideoItem();
  ui.button.dataset.index = "0";
  await toggle(context, ui.button);
  const player = FakeHls.instances[0];

  player.handlers.get(FakeHls.Events.ERROR)(FakeHls.Events.ERROR, { fatal: true });

  assert.equal(player.destroyCalls, 1);
  assert.equal(ui.video.src, "");
  assert.equal(ui.message.textContent, "视频加载失败：媒体播放出错，请重试");
  assert.equal(ui.retry.style.display, "inline-flex");
});

test("closing the detail view destroys all players", async () => {
  const { context, elements } = await loadApp("secret");
  context.fetch = async () => response({ url: "/video/session/master.m3u8", type: "hls" });
  setCurrentPost(context, "article");
  const ui = createVideoItem();
  ui.button.dataset.index = "0";
  await toggle(context, ui.button);
  const player = FakeHls.instances[0];

  vm.runInContext("closePost()", context);

  assert.equal(player.destroyCalls, 1);
  assert.equal(ui.video.src, "");
  assert.equal(elements.get("detail").classList.contains("open"), false);
});

test("a late article response cannot replace a newer detail view", async () => {
  const { context, elements } = await loadApp();
  const oldRequest = deferred();
  context.fetch = async url => {
    if (url === "/api/posts/old") return oldRequest.promise;
    if (url === "/api/posts/new") {
      return response({
        slug: "new", title: "New article", url: "https://cosplaytele.com/new/",
        count: 0, images: [], videos: [], tags: [], categories: [], cosers: [],
      });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  context.oldSlug = "old";
  const oldPending = vm.runInContext("openPost(oldSlug)", context);
  context.newSlug = "new";
  await vm.runInContext("openPost(newSlug)", context);
  oldRequest.resolve(response({
    slug: "old", title: "Old article", url: "https://cosplaytele.com/old/",
    count: 0, images: [], videos: [], tags: [], categories: [], cosers: [],
  }));
  await oldPending;

  assert.equal(elements.get("dTitle").textContent, "New article");
  assert.equal(vm.runInContext("curPost.slug", context), "new");
});

test("video entries link to the original article and start with an online-view button", async () => {
  const { context, elements } = await loadApp();
  context.fetch = async () => response({
    slug: "article", title: "Article", url: "https://cosplaytele.com/article/?a=1&b=2",
    count: 0, images: [], tags: [], categories: [], cosers: [],
    videos: [{ id: "video-id", embed: "https://cossora.stream/embed/private" }],
  });

  context.articleSlug = "article";
  await vm.runInContext("openPost(articleSlug)", context);

  const rendered = elements.get("dBody").innerHTML;
  assert.match(rendered, /href="https:\/\/cosplaytele\.com\/article\/\?a=1&amp;b=2"/);
  assert.doesNotMatch(rendered, /href="https:\/\/cossora\.stream/);
  assert.match(rendered, />在线观看<\/button>/);
  assert.match(rendered, /<video controls playsinline/);
});
