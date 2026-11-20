/* S20 shop effects: one fixed script (hashed in the page's CSP). Everything here only ENHANCES the page: with JavaScript
   off, the menu, the quantity boxes and the order form work exactly as before. Reduced motion: no movement at all.
   Built only from the page's own elements with textContent/cloneNode (no HTML strings). Animations use transform and
   opacity; layout is read once per click or per observer callback, never inside an animation frame. */
(function () {
  try {
    var form = document.getElementById("order-form");
    if (!form) return;
    var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    var hasIO = "IntersectionObserver" in window;
    var rows = Array.prototype.slice.call(form.querySelectorAll(".item"));
    var bar = document.getElementById("bar-order");

    /* ---- add to basket: a dot flies to the basket, which bumps ---- */
    function target() {
      var bl = bar && bar.getElementsByTagName("a")[0];
      if (bl && bl.offsetParent !== null) return bl;
      return document.getElementById("order-h");
    }
    function fly(from) {
      if (reduce || !from || !from.animate) return;
      var t = target();
      if (!t) return;
      var a = from.getBoundingClientRect(), b = t.getBoundingClientRect();
      var x0 = a.left + a.width / 2 - 7, y0 = a.top + a.height / 2 - 7, x1 = b.left + b.width / 2 - 7, y1 = b.top + b.height / 2 - 7;
      var dot = document.createElement("span");
      dot.className = "fly"; dot.setAttribute("aria-hidden", "true");
      document.body.appendChild(dot);
      var up = Math.max(30, Math.abs(y1 - y0) * 0.35);
      var run = dot.animate([
        { transform: "translate(" + x0 + "px," + y0 + "px) scale(1)", opacity: 1 },
        { transform: "translate(" + (x0 + (x1 - x0) * 0.5) + "px," + (Math.min(y0, y1) - up) + "px) scale(1.15)", opacity: 1, offset: 0.5 },
        { transform: "translate(" + x1 + "px," + y1 + "px) scale(.4)", opacity: 0.2 }
      ], { duration: 520, easing: "cubic-bezier(.3,.7,.3,1)" });
      run.onfinish = function () {
        if (dot.parentNode) dot.parentNode.removeChild(dot);
        if (t.animate) t.animate([{ transform: "scale(1)" }, { transform: "scale(1.1)" }, { transform: "scale(1)" }], { duration: 300, easing: "ease-out" });
      };
      if (navigator.vibrate) { try { navigator.vibrate(8); } catch (e) { /* not allowed: fine */ } }
    }
    rows.forEach(function (row) {
      Array.prototype.forEach.call(row.querySelectorAll(".add, .plus"), function (b) {
        b.addEventListener("click", function () { fly(b); });
      });
    });

    /* ---- quick view: a sheet with the item's own details; its stepper drives the real quantity box ---- */
    var dlg = document.createElement("dialog");
    if (typeof dlg.showModal === "function") {
      dlg.className = "qv"; dlg.setAttribute("aria-label", "Item details");
      document.body.appendChild(dlg);
      var current = null;
      var open = function (row) {
        current = row;
        while (dlg.firstChild) dlg.removeChild(dlg.firstChild);
        var body = document.createElement("div"); body.className = "qv-body";
        var img = row.querySelector(".item-photo, .thumb img");
        if (img) {
          var big = document.createElement("img");
          big.src = img.src.replace(/-480\.webp$/, "-1200.webp"); big.alt = img.alt || "";
          body.appendChild(big);
        }
        var h = document.createElement("h3"); h.textContent = row.dataset.item || ""; body.appendChild(h);
        var nb = row.querySelector(".new-badge"); if (nb) body.appendChild(nb.cloneNode(true));
        var fm = row.querySelector(".fm-row"); if (fm) body.appendChild(fm.cloneNode(true));
        var d = row.querySelector(".desc"); if (d) { var p = document.createElement("p"); p.textContent = d.textContent; body.appendChild(p); }
        var pr = document.createElement("div"); pr.className = "qv-price"; pr.textContent = row.querySelector(".price").textContent; body.appendChild(pr);
        var notes = row.querySelector(".item-notes"); if (notes) body.appendChild(notes.cloneNode(true));
        /* S21: one chip + stepper per size / pack (or one stepper); each drives the row's own buttons, so the real
           quantity boxes stay the only thing the form sends. A sold-out item has no stepper. */
        var syncs = [];
        Array.prototype.forEach.call(row.querySelectorAll(".q"), function (q) {
          var input = q.querySelector("input"), lab = q.querySelector(".opt-l");
          var line = document.createElement("div"); line.className = "qv-row" + (lab ? " qv-opt" : "");
          if (lab) {
            var chip = document.createElement("span"); chip.className = "qv-chip";
            var cl = lab.querySelector("span"), cp = lab.querySelector("b");
            chip.textContent = (cl ? cl.textContent : "") + (cp ? "  " + cp.textContent : "");
            line.appendChild(chip);
          }
          var minus = document.createElement("button"); minus.type = "button"; minus.className = "btn btn-line btn-sm"; minus.textContent = "−"; minus.setAttribute("aria-label", "One less " + input.dataset.name);
          var out = document.createElement("output"); out.setAttribute("aria-live", "polite");
          var plus = document.createElement("button"); plus.type = "button"; plus.className = "btn btn-line btn-sm"; plus.textContent = "+"; plus.setAttribute("aria-label", "One more " + input.dataset.name);
          line.appendChild(minus); line.appendChild(out); line.appendChild(plus);
          var add = null;
          if (!lab) { add = document.createElement("button"); add.type = "button"; add.className = "btn btn-primary btn-sm"; add.textContent = "Add to order"; line.appendChild(add); }
          body.appendChild(line);
          var sync = function () { out.textContent = String(parseInt(input.value, 10) || 0); };
          syncs.push(sync);
          var bump = function (btn, which) { var b = q.querySelector(which); if (b) b.click(); syncs.forEach(function (f) { f(); }); if (btn === add || btn === plus) fly(btn); };
          minus.addEventListener("click", function () { if ((parseInt(input.value, 10) || 0) > 0) bump(minus, ".minus"); });
          plus.addEventListener("click", function () { bump(plus, (parseInt(input.value, 10) || 0) ? ".plus" : ".add"); });
          if (add) add.addEventListener("click", function () { bump(add, (parseInt(input.value, 10) || 0) ? ".plus" : ".add"); });
          sync();
        });
        var real = row.querySelector(".choice select");
        if (real) {
          var cw = document.createElement("label"); cw.className = "qv-choice";
          var ct = document.createElement("span"); ct.textContent = (row.querySelector(".choice label") || {}).textContent || "";
          var sel = document.createElement("select");
          Array.prototype.forEach.call(real.options, function (o) { var c = document.createElement("option"); c.value = o.value; c.textContent = o.textContent; sel.appendChild(c); });
          sel.value = real.value;
          sel.addEventListener("change", function () { real.value = sel.value; real.dispatchEvent(new Event("change", { bubbles: true })); });
          cw.appendChild(ct); cw.appendChild(sel); body.appendChild(cw);
        }
        var sold = row.querySelector(".sold-tag"); if (sold) body.appendChild(sold.cloneNode(true));
        var close = document.createElement("button"); close.type = "button"; close.className = "btn btn-line btn-sm qv-close"; close.textContent = "Close";
        body.appendChild(close);
        close.addEventListener("click", function () { dlg.close(); });
        dlg.appendChild(body);
        dlg.showModal();
      };
      dlg.addEventListener("click", function (e) { if (e.target === dlg) dlg.close(); });
      dlg.addEventListener("close", function () { var r = current; current = null; if (r) { var b = r.querySelector(".qv-open"); if (b) b.focus(); } });
      rows.forEach(function (row) {
        var main = row.querySelector(".item-main");
        if (!main) return;
        var b = document.createElement("button");
        b.type = "button"; b.className = "qv-open"; b.textContent = "Details"; b.setAttribute("aria-haspopup", "dialog");
        main.appendChild(b);
        b.addEventListener("click", function () { open(row); });
        row.addEventListener("click", function (e) {
          if (e.target.closest && e.target.closest(".qty, .choice, a, button, input, label, select")) return;
          open(row);
        });
      });
    }

    /* ---- category bar follows the scroll ---- */
    var chips = Array.prototype.slice.call(document.querySelectorAll(".chips .chip"));
    var cats = Array.prototype.slice.call(document.querySelectorAll(".cat[id^='cat-']"));
    if (hasIO && chips.length && cats.length) {
      var spy = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          chips.forEach(function (c) {
            var on = c.getAttribute("href") === "#" + en.target.id;
            if (on) c.setAttribute("aria-current", "true"); else c.removeAttribute("aria-current");
            if (on && c.parentNode && c.parentNode.parentNode) {
              var box = c.parentNode.parentNode;
              if (box.scrollWidth > box.clientWidth) box.scrollLeft = c.offsetLeft - box.clientWidth / 2 + c.offsetWidth / 2;
            }
          });
        });
      }, { rootMargin: "-25% 0px -65% 0px" });
      cats.forEach(function (c) { spy.observe(c); });
    }

    /* ---- gentle reveal; the motif rests while off screen; a New badge shines once ---- */
    var wrap = document.querySelector(".motif-wrap");
    if (hasIO && wrap) {
      new IntersectionObserver(function (en) { wrap.classList.toggle("off", !en[0].isIntersecting); }).observe(wrap);
    }
    if (hasIO && !reduce) {
      var seen = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (!en.isIntersecting) return;
          en.target.classList.add("in"); seen.unobserve(en.target);
        });
      }, { rootMargin: "0px 0px -8% 0px" });
      Array.prototype.forEach.call(document.querySelectorAll(".cat, .gallery, .how .step, .tile"), function (el) {
        if (el.getBoundingClientRect().top < window.innerHeight) return; /* already in view at load: leave it be */
        el.classList.add("pre"); seen.observe(el);
      });
      var shine = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("shine"); shine.unobserve(en.target); } });
      });
      Array.prototype.forEach.call(document.querySelectorAll(".new-badge"), function (el) { shine.observe(el); });
    }
  } catch (e) { /* the page works without any of this */ }
})();
