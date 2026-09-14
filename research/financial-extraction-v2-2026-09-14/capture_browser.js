/* CUA REPL helper used for this bounded acquisition, retained for review.
 * Run only in the documented cua_repl runtime after selecting the existing
 * research tabs and reading their UI. This is not a standalone browser script.
 * Pass the frozen filing-plan jobs loaded from capture_server.py's /plan page.
 * The count includes every original SEC navigation, including retries.
 * Resume copying a loaded document with navigate=false, without spending a new
 * navigation. Never reset the count on a provider reconnect.
 * No browser fetch, CDP, hidden state, credentials, or direct filesystem access.
 */
async function captureOriginal(job, sourceTab, formTab, localUrl, budget, navigate=true) {
  if (navigate) {
    if (budget.used >= 90) throw new Error('Retrieval budget reached');
    budget.used++;
    await sourceTab.goto(job.url);
    await sourceTab.getAXState({emit: false});
  }
  const meta = await sourceTab.playwright.evaluate(() => ({
    chars: document.documentElement.outerHTML.length,
    ix: document.querySelectorAll('[contextref]').length
  }));
  if (!meta.ix) throw new Error('Missing filing facts');
  const chunks = [];
  // A single large returned string was truncated by the browser bridge.
  // Keep each DOM read below that boundary and verify the reconstructed length.
  for (let start = 0; start < meta.chars; start += 150000) {
    chunks.push(await sourceTab.playwright.evaluate(
      ({start}) => document.documentElement.outerHTML.slice(start, start + 150000),
      {start}
    ));
  }
  const markup = chunks.join('');
  if (markup.length !== meta.chars || !markup.endsWith('</html>')) {
    throw new Error('Incomplete document');
  }
  const url = await sourceTab.url();
  if (url !== job.url) throw new Error('Filing URL changed');
  await formTab.goto(localUrl);
  await formTab.getAXState({emit: false});
  await formTab.playwright.getByLabel('Document payload').fill(JSON.stringify({
    id: job.id, url, html: markup,
    document_characters: meta.chars, navigation_attempt: budget.used
  }));
  await formTab.playwright.getByRole('button', {name: 'Save filing', exact: true}).click();
  const state = await formTab.getAXState({emit: false});
  if (!state.includes('Saved filing ' + job.id)) throw new Error('Capture was not confirmed');
  return {id: job.id, navigationAttempts: budget.used};
}
