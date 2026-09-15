<p align="center">
  <img src=".github/assets/aurato-global-payment-icon-pack-banner.png" alt="Aurato Global Payment Icon Pack with payment method, card network, PSP, bank and market icons" width="100%">
</p>

# Aurato Global Payments Icon Pack

**The world of payments - one icon library.**

A searchable, versioned collection of **8,089 payment-related PNG assets** maintained by [Aurato](https://aurato.io):   
**2,073 rounded-square icons** and **6,016 card images**, across **10 categories**. Find payment methods, digital wallets, card networks, payment service providers (PSPs), banks, currencies, markets, regulators, schemes and systems.

[Download ZIP](https://github.com/auratohq/payment-icons/archive/refs/heads/main.zip) · [Contribute](CONTRIBUTING.md) · [Copyright](RIGHTS.md)


## What's included

- Actual PNG files checked into Git with lowercase, human-readable filenames.
- Consistent **256 × 256** primary icons: opaque rounded-square base (**43 px corner radius**), transparent outside corners. The shape is in the image itself - no CSS clipping is needed.
- **406 × 256** card artwork, preserving its card proportions.
- Searchable gallery with filters, light/dark/transparency previews, and individual downloads.
- Machine-readable names, aliases, internal record IDs, repository paths, upstream paths, dimensions, byte sizes, SHA-256 hashes and recorded provenance.
- Reproducible downloads and validation against the approved source snapshot.


## Browse the gallery

Clone or unzip the repository and serve it locally:

```sh
git clone https://github.com/auratohq/payments-icons.git
cd payment-icons
python -m http.server 8000
```

Open **[localhost:8000](http://localhost:8000)**. The gallery has no build step or frontend dependencies. Use an HTTP server; opening `index.html` directly as a `file://` URL cannot fetch its JSON catalog in most browsers.

`index.html`, `gallery/`, `catalog.json`, `catalog/` and the category folders can also be hosted on any static web server. GitHub Pages can serve the repository root after a maintainer enables it in the repository's Pages settings. A live Pages URL is not assumed by this repository.

## Categories

All asset folders are directly at the repository root.

| Folder | Assets | Shape |
| --- | ---: | --- |
| [banks](banks/) | 136 | Rounded square |
| [cards](cards/) | 6,016 | Card |
| [currencies](currencies/) | 153 | Rounded square |
| [markets](markets/) | 250 | Rounded square |
| [operators](operators/) | 88 | Rounded square |
| [payment-methods](payment-methods/) | 1,006 | Rounded square |
| [psps](psps/) | 75 | Rounded square |
| [regulators](regulators/) | 255 | Rounded square |
| [schemes](schemes/) | 91 | Rounded square |
| [systems](systems/) | 19 | Rounded square |

## Usage

### HTML

Copy the relevant file into your application's public assets:

```html
<img src="/payment-methods/paypal.png" alt="paypal payment method icon" width="45" height="45">
```

For cards, keep the native aspect ratio:

```css
.payment-icon { width: 45px; height: 45px; object-fit: contain; }
.card-art { height: 45px; width: auto; object-fit: contain; }
```

### React

```jsx
export function PaymentIcon({ slug, name }) {
  return <img src={`/payment-methods/${slug}.png`} alt={`${name} payment method icon`} width={45} height={45} />;
}
```

### Raw GitHub URL

For a quick prototype:

```text
https://raw.githubusercontent.com/auratohq/payment-icons/main/payment-methods/paypal.png
```

`main` changes over time. For reproducible use, replace `main` with a reviewed commit SHA, or vendor the files into your own deployment. The repository is a snapshot; Aurato's public Supabase asset library remains the upstream source.

### Read the catalog

`catalog.json` is a small index referencing one JSON array per category. Paths are relative to the repository root.

```js
const index = await fetch('/catalog.json').then(r => r.json());
const category = index.categories.find(c => c.id === 'payment-methods');
const icons = await fetch('/' + category.path).then(r => r.json());
const paypal = icons.find(icon => icon.name === 'paypal');
console.log(paypal.path, paypal.upstreamPath, paypal.sha256, paypal.source.kind);
```

See [the catalog specification](catalog/README.md) for fields and [the asset schema](catalog/asset.schema.json). `catalog.csv` contains the same records in one spreadsheet-friendly file; formula-like text values are prefixed with an apostrophe for spreadsheet safety.

## Validation and updates

Python 3.11+ and Pillow are used for maintenance only. Consumers and the gallery do not need them.

```sh
python -m pip install -r requirements.txt
python scripts/collection.py validate
python -m unittest discover -s scripts -p 'test_*.py'
```

Validation checks every file for its expected path, byte size, SHA-256, PNG dimensions and alpha shape. It rejects unlisted files and missing icons. Pixel validation checks primary icons' opaque interior and transparent corners, with tolerance only along the anti-aliased edge. Card images use separate checks.

To restore missing files from the committed snapshot:

```sh
python scripts/collection.py download
python scripts/collection.py validate
```

Downloads use public URLs, require no API key, and reject changed bytes. [Contribution instructions](CONTRIBUTING.md) explain how maintainers export and review a new upstream snapshot. These scripts never change Supabase Storage.

## Rights

The gallery, scripts and documentation are [MIT licensed](LICENSE). **PNG assets and third-party artwork are excluded from that license.** Brand names, logos and card designs belong to their respective owners. Inclusion does not imply endorsement or grant trademark or artwork rights. 
See [RIGHTS.md](RIGHTS.md) for provenance, intended use, corrections and removal requests.

---

Built and maintained by [Aurato](https://aurato.io) — understand how money moves, anywhere.
