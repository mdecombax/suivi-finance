// Configuration Firebase pour le frontend
import { initializeApp } from 'https://www.gstatic.com/firebasejs/9.23.0/firebase-app.js';
import {
  getAuth,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider,
  signOut,
  onAuthStateChanged,
  updateProfile
} from 'https://www.gstatic.com/firebasejs/9.23.0/firebase-auth.js';
import {
  getFirestore,
  collection,
  addDoc,
  getDocs,
  deleteDoc,
  doc,
  query,
  orderBy
} from 'https://www.gstatic.com/firebasejs/9.23.0/firebase-firestore.js';

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
const app = initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);

// Provider Google
const googleProvider = new GoogleAuthProvider();

// État de l'authentification
let currentUser = null;
let authStateListeners = [];

// Fonctions d'authentification
export const authFunctions = {
  // Connexion avec email/password
  async signInWithEmail(email, password) {
    try {
      const userCredential = await signInWithEmailAndPassword(auth, email, password);
      return { success: true, user: userCredential.user };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // Connexion avec Google
  async signInWithGoogle() {
    try {
      const result = await signInWithPopup(auth, googleProvider);
      return { success: true, user: result.user };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // Inscription avec email/password
  async signUpWithEmail(email, password, displayName) {
    try {
      const userCredential = await createUserWithEmailAndPassword(auth, email, password);
      // Mettre à jour le nom d'affichage
      if (displayName) {
        await updateProfile(userCredential.user, { displayName });
      }
      return { success: true, user: userCredential.user };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // Déconnexion
  async signOut() {
    try {
      await signOut(auth);
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
export const firestoreFunctions = {
  // Ajouter un ordre
  async addOrder(userId, orderData) {
    try {
      const docRef = await addDoc(collection(db, 'users', userId, 'orders'), {
        ...orderData,
        createdAt: new Date(),
        updatedAt: new Date()
      });
      return { success: true, id: docRef.id };
    } catch (error) {
      return { success: false, error: error.message };
    }
  },

  // Récupérer les ordres d'un utilisateur
  async getOrders(userId) {
    try {
      const ordersRef = collection(db, 'users', userId, 'orders');
      const q = query(ordersRef, orderBy('date', 'asc'));
      const querySnapshot = await getDocs(q);
      
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
      await deleteDoc(doc(db, 'users', userId, 'orders', orderId));
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }
};

// Écouter les changements d'état d'authentification
onAuthStateChanged(auth, (user) => {
  currentUser = user;
  authStateListeners.forEach(callback => callback(user));
});

// Exporter les instances pour usage externe
export { auth, db, app };
