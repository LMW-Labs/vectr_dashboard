// Import the functions you need from the SDKs you need
import { initializeApp } from "firebase/app";
import { getAuth } from "firebase/auth";

// Your web app's Firebase configuration
const firebaseConfig = {
  apiKey: "AIzaSyCPH_gPkyBCzHct-vgGzHRn5-6T2FA7csQ",
  authDomain: "vectr-dashboard.firebaseapp.com",
  projectId: "vectr-dashboard",
  storageBucket: "vectr-dashboard.firebasestorage.app",
  messagingSenderId: "367998317739",
  appId: "1:367998317739:web:a2aef87997adc5f3fdf3ee",
  measurementId: "G-LJMDJER171"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Firebase Authentication and get a reference to the service
export const auth = getAuth(app);
