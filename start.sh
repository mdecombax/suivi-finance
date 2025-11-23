#!/bin/bash

# Script de démarrage pour Suivi Finance avec modèle freemium

echo "🚀 Démarrage de Suivi Finance..."

# Activer l'environnement virtuel
echo "📦 Activation de l'environnement virtuel..."
source venv/bin/activate

# Vérifier si Stripe est installé
if ! python -c "import stripe" 2>/dev/null; then
    echo "📥 Installation de Stripe..."
    pip install stripe
fi

# Vérifier si le fichier .env existe
if [ ! -f .env ]; then
    echo "⚠️  Fichier .env manquant !"
    echo "📋 Copiez .env.example vers .env et configurez vos clés Stripe:"
    echo "   cp .env.example .env"
    echo "   nano .env"
    echo ""
    echo "📖 Consultez STRIPE_SETUP.md pour la configuration complète"
    echo ""
fi

# Démarrer l'application
echo "🌟 Lancement de l'application..."
echo "📱 Accédez à http://localhost:8000"
echo "💳 Page d'abonnement : http://localhost:8000/subscription"
echo ""
echo "🛑 Appuyez sur Ctrl+C pour arrêter"

python app.py