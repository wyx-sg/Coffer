# Documentation screenshots

How other products keep product pictures in their docs and on their home pages
current. Written for the ADR [Docs Screenshots Are Generated From a Seeded
Daemon](../decisions/docs-screenshots-are-generated-from-a-seeded-daemon.md).

## Mechanisms

**Style guide, hand capture (GitHub Docs).** A screenshot is added only when a
UI element is hard to find; the rule sheet says to crop to the element with just
enough context, prefer the light theme, replace the account with a placeholder,
leave the cursor out, use PNG at 750 to 1000 px wide and no more than 250 KB,
keep complete instructions in the text, and write alt text. A replaced image
keeps its filename. Nothing in the process notices when the UI moves.
Source: [GitHub Docs, creating screenshots](https://docs.github.com/en/enterprise-server@3.22/contributing/writing-for-github-docs/creating-screenshots).

**End-to-end tests that emit the images (CloudCannon).** Their tests load the
real app, set up state (open a modal, fill data), capture a webp with a
predictable name, and the docs refer to the image by key through a `DocShot`
component. About 700 images, 207 articles; the images refresh when the tests
re-run. Costs they report: a scenario per image, flaky tests to fix, third-party
screens still manual. The tests also became integration coverage.
Source: [CloudCannon community post](https://community.cloudcannon.com/t/100-automated-screenshot-coverage-in-our-documentation/493).

**Scripted batches (shot-scraper).** A YAML file lists URL, selector and output
file; a JavaScript step can open a menu or remove elements before capture; run
daily in CI and commit the new images. Built on Playwright, suited to pages that
a URL can reach.
Source: [Simon Willison on shot-scraper](https://simonwillison.net/2022/Mar/10/shot-scraper/).

**What to automate, what to review.** Automate repeatable states where staleness
costs most (setup, connect, settings), capture the panel a step describes
rather than a window, wait on an explicit ready signal rather than a delay, and
keep a manifest per shot. A person still reviews whether the image teaches the
step and is fit to publish; generation and publishing are separate jobs.
Source: [Playwright screenshots for documentation](https://dev.to/jakexkim/playwright-screenshots-for-documentation-what-to-automate-and-what-to-review-3h44).

**Interactive demos.** Product-demo tools sit on a spectrum: screenshot
click-throughs (fastest, least faithful), recordings (polished, fixed), and HTML
captures that clone the product's markup so it can be clicked and zoomed
(most convincing, heaviest). The comparisons are written by vendors.
Sources: [Supademo](https://supademo.com/features/html-recorder), [Arcade](https://www.arcade.software/post/best-interactive-demo-software-2026).

## Worth borrowing / worth avoiding

- Borrow: images produced by the test suite and referenced by name, so a UI
  change re-runs one command (CloudCannon); crop to what a step describes and
  keep the instructions in text (GitHub Docs).
- Borrow: a human reviews the image diff before it ships.
- Avoid: hand capture as the only mechanism, which is what leaves a picture
  contradicting the product.
- Defer: an embedded live replica, which needs a mock API layer first.
