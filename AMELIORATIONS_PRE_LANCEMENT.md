# Améliorations Pré-Lancement - Suivi Finance

## 🎨 Branding & Identité Visuelle

### Nom du Produit
- [ ] Trouver un nom correct et professionnel pour l'application
- [ ] Vérifier la disponibilité du domaine

### Logo & Favicon
- [ ] Créer un logo professionnel
- [ ] Créer une favicon
- [ ] Intégrer le logo dans l'application
- [ ] Mettre à jour les métadonnées HTML avec la favicon

---

## ⚡ Performance & Chargement

### Graphiques
- [ ] **URGENT** Optimiser le chargement du graphique de la page d'accueil (actuellement trop lent)


### Animations
- [ ] Rendre l'animation de chargement des ordres plus fluide et premium
- [ ] Optimiser les transitions globales

---

## 🐛 Corrections de Bugs & Données

### Page Détails des Positions
- [ ] Corriger les frais de gestion (valeurs incorrectes)
- [ ] Corriger les plus/moins-values. L'air qui est affiché lors d'une moins-value d'être affiché en rouge et celui d'une plus-value d'être affiché en vert comme le graphique qui se trouve sur la page portefeuille.
- [ ] Vérifier la cohérence de tous les chiffres affichés Entre la page portefeuille et la page Détails des Positions
- [ ] Récupérer l'animation de chargement du graphique sur la page portefeuille pour la mettre sur le graphique des pages Page Détails des Positions
---

## 🎨 Interface & UX

### Mode Clair (Light Mode)
- [ ] Corriger les problèmes d'affichage en mode clair
- [ ] Vérifier tous les composants en mode clair
- [ ] S'assurer d'un contraste suffisant

### Profil Utilisateur
- [ ] Corriger l'affichage de l'email qui s'affiche sur deux lignes
  - L'email doit s'afficher sur une seule ligne
  - Doit fonctionner quelle que soit la taille de l'écran
  - Utiliser text-overflow: ellipsis si nécessaire

---

## 🔧 Architecture & Refactoring

### Menu Paramètres (Settings)
**PRIORITÉ HAUTE** - Centraliser le code

- [ ] Le bouton paramètres ne fonctionne pas sur :
  - Page Ordres
  - Page Projection
- [ ] Créer un composant unique pour le menu paramètres qui doit être identique au composant lorsque l'on clique sur la Photo de profil sur la page portefeuille
- [ ] Importer ce composant sur toutes les pages
- [ ] S'assurer que toutes les modales se chargent de la même manière
- [ ] Toute modification du composant doit se répercuter automatiquement sur toutes les pages

**Localisation recommandée:**
- Créer un composant `SettingsMenu.jsx` ou `SettingsModal.jsx` dans `/components/shared/`
- Importer sur chaque page qui en a besoin

### Bouton Éclair (Action Rapide)
**PRIORITÉ HAUTE** - Centraliser le code

- [ ] Le bouton éclair doit être disponible sur toutes les pages
- [ ] Créer un composant unique pour ce bouton
- [ ] Importer ce composant sur toutes les pages
- [ ] S'assurer qu'une modification se répercute partout automatiquement

**Localisation recommandée:**
- Créer un composant `QuickActionButton.jsx` dans `/components/shared/`
- Ou l'intégrer dans un layout global


**Localisation recommandée:**
- Créer un composant `UserProfileMenu.jsx` dans `/components/shared/`
- Ou l'intégrer dans un header/navbar global

---

## 📋 Checklist de Validation Finale

### Tests Globaux
- [ ] Tester toutes les pages en mode clair et sombre
- [ ] Vérifier la cohérence des données entre toutes les pages
- [ ] Tester sur différentes tailles d'écran (mobile, tablette, desktop)
- [ ] Vérifier les performances de chargement
- [ ] Tester tous les boutons et interactions

### Composants Centralisés
- [ ] Vérifier que les modifications sur les composants partagés se répercutent partout
- [ ] Documenter les composants partagés créés
- [ ] S'assurer qu'aucun code n'est dupliqué

### Qualité du Code
- [ ] Nettoyer le code inutilisé
- [ ] Optimiser les imports
- [ ] Vérifier les console.log et les retirer
- [ ] Documenter les fonctions complexes

---

## 🚀 Prêt pour le Lancement

Une fois tous ces points validés, l'application sera prête pour le lancement.

**Date cible:** [À définir]
**Responsable:** [À définir]

---

_Document créé le 23 novembre 2025_
_Dernière mise à jour: 23 novembre 2025_
