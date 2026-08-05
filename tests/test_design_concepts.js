const fs = require("fs");

const prototypePath = process.argv[2];
if (!prototypePath) {
  throw new Error("usage: node tests/test_design_concepts.js <dashboard-concepts.html>");
}

const html = fs.readFileSync(prototypePath, "utf8");
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) {
  throw new Error("dashboard concept file does not contain a script");
}
new Function(scriptMatch[1]);

const requiredFragments = [
  'data-concept="clarity"',
  'data-concept="signal"',
  'data-concept="folio"',
  'data-concept="spectral"',
  "01 · Clarity",
  "02 · Signal Room",
  "03 · Folio",
  "04 · Spectral",
  "function setConcept",
  "function applyCandidateFilter",
  'class="review-shell"',
  "Assisted review",
  'class="spark" aria-hidden="true"><svg viewBox="0 0 24 24"',
  "Exact quotation verified in work experience",
  "Your final decision",
  "@media (max-width: 780px)",
  "prefers-reduced-motion",
  'class="career-connector"',
  'class="career-particle"',
  "animation: career-flow-down 4.2s linear infinite",
  "animation-delay: -1.4s",
  "animation-delay: -2.8s",
  "--career-axis: 80px",
  "height: calc(100% + var(--career-gap))",
];

for (const fragment of requiredFragments) {
  if (!html.includes(fragment)) {
    throw new Error(`missing dashboard concept fragment: ${fragment}`);
  }
}

const concepts = html.match(/class="concept-btn" data-concept=/g) || [];
if (concepts.length !== 4) {
  throw new Error(`expected exactly four concept selectors, found ${concepts.length}`);
}

console.log("dashboard concepts check passed");
