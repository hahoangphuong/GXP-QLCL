// Run this read-only probe in a real browser page with the actual App mounted.
// jsdom has no layout engine; its zero-valued geometry cannot validate overflow.
// Call with { assert: false } to record a failing baseline, then without arguments
// to assert after the fix. Save the returned measurements outside Git.
function headerOverflowRegression(options) {
  const assert = options?.assert ?? true;
  const root = document.documentElement;
  const header = document.querySelector(".topbar");
  if (!header) throw new Error("Actual App header must be mounted before measuring");
  const boxes = Array.from(document.querySelectorAll(".shell-chrome, .topbar, .topbar *"), element => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return { selector: element.className || element.tagName, left: rect.left, right: rect.right,
      width: rect.width, clientWidth: element.clientWidth, scrollWidth: element.scrollWidth,
      overflowX: style.overflowX };
  }).filter(box => box.width > 0);
  const failures = [];
  if (root.scrollWidth > root.clientWidth) failures.push("Document has horizontal overflow");
  // One CSS pixel permits fractional layout rounding, not document overflow.
  for (const box of boxes) if (box.right > root.clientWidth + 1 || box.left < -1)
    failures.push(`Header element outside document: ${box.selector}`);
  if (innerWidth <= 760) {
    for (const element of document.querySelectorAll("html, body, #root, .app-shell, .shell-chrome, .topbar")) {
      if (["hidden", "clip"].includes(getComputedStyle(element).overflowX))
        failures.push(`Page/header clipping conceals overflow: ${element.className || element.tagName}`);
    }
  }
  const result = { viewport: { width: innerWidth, height: innerHeight }, clientWidth: root.clientWidth,
    scrollWidth: root.scrollWidth, boxes, passed: failures.length === 0, failures };
  if (assert && !result.passed) throw new Error(JSON.stringify(result));
  return result;
}
