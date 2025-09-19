# Suivi Finance

Application de suivi de portefeuille d'investissement avec authentification Firebase et stockage Firestore.

## 🚀 Installation

### 1. Prérequis
- Python 3.8+
- Node.js 16+
- Compte Firebase

### 2. Installation des dépendances

#### Backend (Python)
```bash
# Activer l'environnement virtuel
source venv/bin/activate

# Installer les dépendances Python
pip install -r requirements.txt
```

#### Frontend (JavaScript)
```bash
# Installer les dépendances Node.js
npm install
```

### 3. Configuration Firebase

1. **Créer un projet Firebase** sur [console.firebase.google.com](https://console.firebase.google.com)
2. **Activer Authentication** avec Email/Password et Google
3. **Créer une base de données Firestore** en mode production
4. **Configurer les règles de sécurité** :

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /users/{userId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
    
    match /users/{userId}/orders/{orderId} {
      allow read, write: if request.auth != null && request.auth.uid == userId;
    }
  }
}
```

5. **Télécharger la clé de service** et la placer dans le répertoire racine
6. **Récupérer la configuration web** et la mettre dans `firebase-config.json`

### 4. Lancement de l'application

```bash
# Démarrer le serveur Flask
python app.py
```

L'application sera accessible sur `http://localhost:5050`

## 📁 Structure du projet

```
suivi-finance/
├── app.py                          # Application Flask principale
├── requirements.txt                 # Dépendances Python
├── package.json                    # Dépendances Node.js
├── firebase-config.json            # Configuration Firebase frontend
├── suivi-financ-firebase-adminsdk-*.json  # Clé de service Firebase
├── services/
│   ├── firebase_service.py         # Service Firestore
│   └── auth_service.py             # Service d'authentification
├── static/
│   └── js/
│       └── firebase-config.js      # Configuration Firebase frontend
└── templates/
    ├── index.html                  # Page principale (portefeuille)
    ├── orders.html                 # Page de gestion des ordres
    ├── login.html                  # Page de connexion
    └── register.html               # Page d'inscription
```

## 🔧 Fonctionnalités

### Authentification
- Connexion avec email/mot de passe
- Connexion avec Google
- Inscription de nouveaux utilisateurs
- Gestion des sessions

### Gestion du portefeuille
- Affichage des KPIs (Total investi, Valeur actuelle, P/L, Performance)
- Analyse fiscale (PEA vs CTO)
- Tableau des positions agrégées
- Calcul de performance avec XIRR

### Gestion des ordres
- Ajout d'ordres d'investissement
- Historique des ordres
- Suppression d'ordres
- Validation des données (ISIN, prix, quantités)

### Données
- Stockage sécurisé dans Firestore
- Isolation des données par utilisateur
- Synchronisation temps réel
- Sauvegarde automatique

## 🔒 Sécurité

- Authentification Firebase obligatoire
- Règles Firestore restrictives
- Validation des données côté client et serveur
- Tokens JWT pour l'authentification API
- CORS configuré pour les requêtes frontend

## 🌐 API Endpoints

### Authentification
- `POST /api/auth/verify` - Vérifier un token d'authentification

### Portefeuille
- `GET /api/portfolio` - Récupérer les données du portefeuille
- `POST /api/portfolio` - Mettre à jour le type de compte

### Ordres
- `GET /api/orders` - Récupérer tous les ordres
- `POST /api/orders` - Ajouter un nouvel ordre
- `DELETE /api/orders?order_id=xxx` - Supprimer un ordre

## 🎨 Interface

- Design moderne et responsive
- Mode sombre/clair
- Animations fluides
- Interface intuitive
- Messages d'erreur/succès

## 📱 Responsive

L'application s'adapte à tous les écrans :
- Desktop (1200px+)
- Tablet (768px - 1199px)
- Mobile (< 768px)

## 🚀 Déploiement

### Variables d'environnement
```bash
export FLASK_ENV=production
export FLASK_DEBUG=False
```

### Firestore
- Configurer les règles de sécurité
- Activer l'indexation automatique
- Configurer les quotas

### Authentification
- Configurer les domaines autorisés
- Activer les fournisseurs d'authentification
- Configurer les paramètres de sécurité

## 📊 Données

### Structure des ordres
```json
{
  "isin": "FR0012345678",
  "quantity": 10,
  "unitPrice": 25.50,
  "totalPriceEUR": 255.00,
  "date": "2024-01-15",
  "createdAt": "2024-01-15T10:30:00Z",
  "updatedAt": "2024-01-15T10:30:00Z"
}
```

### Structure des utilisateurs
```json
{
  "email": "user@example.com",
  "displayName": "John Doe",
  "createdAt": "2024-01-15T10:30:00Z",
  "lastLogin": "2024-01-15T10:30:00Z"
}
```

## 🔧 Développement

### Ajout de nouvelles fonctionnalités
1. Modifier `app.py` pour les routes backend
2. Mettre à jour les services Firebase si nécessaire
3. Modifier les templates HTML
4. Ajouter les styles CSS
5. Tester l'authentification et les permissions

### Debug
- Activer le mode debug Flask
- Vérifier les logs Firebase
- Utiliser les outils de développement du navigateur
- Vérifier les règles Firestore

## 📝 Licence

MIT License - Voir le fichier LICENSE pour plus de détails.
