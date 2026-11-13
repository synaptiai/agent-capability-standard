// A built page's template, from its body's `page--<template>` class. The
// `page--with-*` and `page--no-*` classes are layout modifiers, not templates.
// Shared by check-dist.mjs (which reads the HTML) and check-runs.mjs (which
// reads the class list in the browser and passes it back).

/** The template named by a class list, or null when it names none. */
export function templateOf(classes) {
  const t = classes.find((c) => c.startsWith('page--') && !c.startsWith('page--with') && !c.startsWith('page--no-'));
  return t ? t.slice('page--'.length) : null;
}

/** The body's class list of a page's HTML ([] when the body has no class). */
export function bodyClasses(html) {
  const cls = /<body\b[^>]*\sclass="([^"]*)"/.exec(html)?.[1] ?? '';
  return cls.split(/\s+/).filter(Boolean);
}
