import React from "react";
import ReactDOM from "react-dom/client";
import {BrowserRouter} from 'react-router-dom';
import App from './App.jsx';
import {UiProvider} from './context/UiContext.jsx';
import {AuthProvider} from './context/AuthContext.jsx';
import './styles.css';

ReactDOM.createRoot(document.getElementById("root")).render(
    <React.StrictMode>
        <BrowserRouter>
            <UiProvider>
                <AuthProvider>
                    <App />
                </AuthProvider>
            </UiProvider>
        </BrowserRouter>
    </React.StrictMode> 
);
