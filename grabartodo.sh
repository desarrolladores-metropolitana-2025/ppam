git checkout main
git add .
git commit -m "Correcciones"
git push origin main
git checkout desarrollo_PPAM
git reset --hard main
git push -f origin desarrollo_PPAM
git checkout main

