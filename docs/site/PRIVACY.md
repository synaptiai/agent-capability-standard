# Privacy

This page describes what happens when you visit this site. It covers the
documentation site only, not the GitHub repository or other sites it links to.

## No cookies, no analytics

The site sets no cookies. It runs no analytics, tracking or advertising
scripts, and it loads no script from another site: every script on a page is
served by this site and runs the page's own controls. Search runs in
your browser against an index served by this site; what you type is not sent
anywhere.

## What your browser stores

Two values are kept in your browser, and only there:

- **Theme:** if you choose the light or dark theme, the choice is saved in
  your browser's local storage under `acs-theme` so the next page uses it.
  Choosing "system" removes it.
- **Sidebar position:** the scroll position of the sidebar is kept in session
  storage while the tab is open, so the sidebar does not jump between pages.

Neither value is sent to the site. You can clear both by clearing the site
data in your browser.

## Requests to other sites

The overview page shows four badges from `img.shields.io`, so opening that
page makes your browser request those images from that service, which then
sees your IP address and browser details. No other page loads anything from
another site unless you follow a link.

## Hosting and request logs

The site is served by Cloudflare. Like any web host, Cloudflare processes
each request (your IP address, the page requested, your browser's user agent
and the time) to deliver the page and protect the site from abuse, and keeps
request logs under its own policies. The response headers also ask browsers
to send Cloudflare network error reports when a page fails to load. The
publisher of this site does not run analytics on these logs.

## Questions

Ask about this page through the [repository's issue tracker](https://github.com/synaptiai/agent-capability-standard/issues),
as described under [Contact](CONTACT.md).
