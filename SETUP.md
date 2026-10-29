# Setup (5 minutes)

1. **Create the repo.** On GitHub, make a **public** repo named exactly your username (`USERNAME/USERNAME`). Push all of these files to it, including the `.github/` folder.
2. **Edit `config.json`.** Set `github_username`, plus your `birthday` (`YYYY-MM-DD`) if you want Uptime to show your age. Fill in Email and LinkedIn. Empty values are hidden.
3. **Edit `README.md`.** Replace `YOUR_GITHUB_USERNAME` (it appears twice).
4. **Make a token.** Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic). Create one with the `repo` and `read:user` scopes, and set the expiration to whatever you're comfortable with. If you only want public repos counted, use `public_repo` + `read:user`.
5. **Add the token as a secret.** In the repo, go to Settings → Secrets and variables → Actions → New repository secret. Name it `ACCESS_TOKEN` and paste the token.
6. **Run it.** Go to Actions → "Update profile card" → **Run workflow**. After that it updates daily, and again whenever you push changes to `config.json`, `ascii.txt`, `ascii_dark.txt` or `card.py`.

## Your photo → ASCII
The card draws two portraits: `ascii.txt` (dark ink, light card) and `ascii_dark.txt`
(light ink, dark card). Start from a PNG with the background removed (transparent)
so the background stays blank in both. `portrait.png` is the current one.
```bash
pip install pillow
python make_ascii.py portrait.png --equalize --contrast 1.0                  # -> ascii.txt
python make_ascii.py portrait.png --contrast 1.3 --invert -o ascii_dark.txt  # -> ascii_dark.txt
python card.py --demo                  # preview locally with fake stats
```
Also try `--width 120` (more detail), or drop `--equalize` / change `--contrast`. **New photo? Regenerate both files**
(or delete `ascii_dark.txt`, and the dark card will reuse `ascii.txt`), otherwise the dark card keeps the old face.
To cut out the background yourself: `pip install "rembg[cpu,cli]"`, then `rembg i -m u2net_human_seg me.jpg portrait.png`.
Then hand-tweak the .txt files if any stray characters bug you.

## Notes
- The first run is slow on lines of code because it walks every commit. After that, `cache/loc.json` makes it fast. Repo names in the cache are hashed, so private repo names don't leak.
- "Commits" counts your commits on the default branch of every repo your token can see.
- Lines too long for the card trigger a warning in the Action log. If you see one, shorten the value in `config.json`.
