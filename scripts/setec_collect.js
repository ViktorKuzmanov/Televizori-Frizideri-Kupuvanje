// Собира цени од Сетек. Се извршува во прелистувач, на отворена страница од setec.mk
// (на пр. https://setec.mk/category/televizori-55). Страниците се подредени од најевтин.
// Ги минува страниците сè додека цената не надмине MAX и враќа текст (TSV):
//   slug<TAB>модел<TAB>цена<TAB>редовна
// Тој текст Claude го зачувува во data/manual/setec-<cat>.tsv (прва линија: # датум),
// а scripts/fetch_prices.py го спојува со другите продавници.
//
// Употреба: await setecCollect('televizori-55', 'tv', 45000)
//           await setecCollect('kombinirani-20frizhideri-98', 'fridge', 50000)
async function setecCollect(slug, cat, MAX) {
  const extract = () => {
    const seen = new Set(), out = [];
    for (const a of document.querySelectorAll('a[href^="/products/"]')) {
      const h = a.getAttribute('href'); if (seen.has(h)) continue;
      let c = a; for (let i = 0; i < 8 && c.parentElement; i++) { c = c.parentElement; if (c.innerText.includes('Редовна')) break; }
      const t = c.innerText; if (!t.includes('Редовна')) continue; seen.add(h);
      const L = t.split('\n').map(s => s.trim()).filter(Boolean);
      const num = s => s ? parseInt(s.replace(/\D/g, '')) : null;
      const club = (t.match(/Клуб цена:\s*([\d.]+)/) || [])[1];
      const reg = (t.match(/Редовна цена:\s*([\d.]+)/) || [])[1];
      const inst = t.match(/(\d+) x ([\d.]+) ден/) || [];
      const img = c.querySelector('img[alt]:not([alt=Badge])');
      const iB = L.findIndex(x => !/^-?\d+%$/.test(x));
      let image = img ? (img.currentSrc || img.src) : null;
      if (image && image.includes('url=')) image = decodeURIComponent(image.replace(/^.*url=/, '').replace(/&w=.*$/, ''));
      out.push({ slug: h.split('/').pop(), url: 'https://setec.mk' + h, brand: L[iB], model: L[iB + 1],
        price: num(club) || num(reg), regular: num(reg), monthly: num(inst[2]), installments: inst[1] ? +inst[1] : null,
        image: image && image.startsWith('http') ? image : null });
    }
    return out;
  };
  const all = [];
  for (let p = 1; p <= 40; p++) {
    window.next.router.push(`/category/${slug}?page=${p}`);
    let got = [];
    for (let w = 0; w < 24; w++) {
      await new Promise(r => setTimeout(r, 500));
      got = extract();
      if (got.length && !all.some(x => x.slug === got[0].slug)) break;
      got = [];
    }
    if (!got.length) break;
    all.push(...got);
    if (got.at(-1).price > MAX) break;
  }
  return all.filter(x => x.price <= MAX)
    .map(x => [x.slug, x.model, x.price, x.regular].join('\t')).join('\n');
}
