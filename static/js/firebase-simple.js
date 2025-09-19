// Configuration Firebase simplifiée avec CDN
// Ce fichier doit être chargé après les CDN Firebase

// Configuration Firebase
const firebaseConfig = {
  apiKey: "AIzaSyBFrk8tZVEuM0LeQ0D8kJ7N2Bt-KyuQv0I",
  authDomain: "suivi-financ.firebaseapp.com",
  projectId: "suivi-financ",
  storageBucket: "suivi-financ.firebasestorage.app",
  messagingSenderId: "959011615445",
  appId: "1:959011615445:web:993be6cee77fc6cedae85c",
  measurementId: "G-8QXCJ8J23S"
};

// Initialiser Firebase
const app = firebase.initializeApp(firebaseConfig);
const auth = firebase.auth();
const db = firebase.firestore();

// État de l'authentification
let currentUser = null;
let authStateListeners = [];

// Fonctions d'authentification
const authFunctions = {
  // Connexion avec email/password
  async signInWithEmail(email, password) {
    try {
      const userCredential = await auth.signInWithEmailAndPassword(email, password);
      return { success: true, user: userCredential.user };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // Connexion avec Google
  async signInWithGoogle() {
    try {
      const provider = new firebase.auth.GoogleAuthProvider();
      const result = await auth.signInWithPopup(provider);
      return { success: true, user: result.user };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // Inscription avec email/password
  async signUpWithEmail(email, password, displayName) {
    try {
      const userCredential = await auth.createUserWithEmailAndPassword(email, password);
      // Mettre à jour le nom d'affichage
      if (displayName) {
        await userCredential.user.updateProfile({ displayName });
      }
      return { success: true, user: userCredential.user };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // Déconnexion
  async signOut() {
    try {
      await auth.signOut();
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // Obtenir l'utilisateur actuel
  getCurrentUser() {
    return currentUser;
  },

  // Écouter les changements d'état d'authentification
  onAuthStateChanged(callback) {
    authStateListeners.push(callback);
    return () => {
      const index = authStateListeners.indexOf(callback);
      if (index > -1) {
        authStateListeners.splice(index, 1);
      }
    };
  }
};

// Fonctions Firestore
const firestoreFunctions = {
  // Ajouter un ordre
  async addOrder(userId, orderData) {
    try {
      const docRef = await db.collection('users').doc(userId).collection('orders').add({
        ...orderData,
        createdAt: firebase.firestore.FieldValue.serverTimestamp(),
        updatedAt: firebase.firestore.FieldValue.serverTimestamp()
      });
      return { success: true, id: docRef.id };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // Récupérer les ordres d'un utilisateur
  async getOrders(userId) {
    try {
      const querySnapshot = await db.collection('users').doc(userId).collection('orders')
        .orderBy('date', 'asc')
        .get();
      
      const orders = [];
      querySnapshot.forEach((doc) => {
        orders.push({ id: doc.id, ...doc.data() });
      });
      
      return { success: true, orders };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // Supprimer un ordre
  async deleteOrder(userId, orderId) {
    try {
      await db.collection('users').doc(userId).collection('orders').doc(orderId).delete();
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }
};

// Écouter les changements d'état d'authentification
auth.onAuthStateChanged((user) => {
  currentUser = user;
  authStateListeners.forEach(callback => callback(user));
});

// Exporter les fonctions pour usage global
window.authFunctions = authFunctions;
window.firestoreFunctions = firestoreFunctions;
window.firebase = firebase;
