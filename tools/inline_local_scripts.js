// Test helper (v1.9.62): jsdom does not fetch <script src>, so pages that rely on the site's own
// shared scripts (chooser.js) get those files inlined before parsing. Only same-site files listed
// here are inlined; CDN scripts and deferred mobile.js are left alone, as before.
const fs = require("fs"), path = require("path");
const LOCAL = ["chooser.js", "percapita.js"];  // v1.9.118: percapita.js
module.exports = function inlineLocalScripts(html, root){
  return html.replace(/<script src="([a-z0-9_-]+\.js)(?:\?v=\d+)?"><\/script>/g, (tag, file) => {
    if(LOCAL.indexOf(file) === -1) return tag;
    const src = fs.readFileSync(path.join(root || process.cwd(), file), "utf8");
    return "<script>" + src.replace(/<\/script/gi, "<\\/script") + "</script>";
  });
};
