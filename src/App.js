// src/App.js
import React from 'react';
import { createTheme, ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import DashboardLayout from './DashboardLayout';

const theme = createTheme({
  palette: {
    mode: 'dark', // Use a dark theme for better contrast with the new background
    primary: {
      main: '#36deef', // A vibrant color from your logo for primary actions
    },
    background: {
      default: '#09111d', // Fallback color from your gradient
    },
    text: {
      primary: '#ffffff',
      secondary: '#b0b0b0',
    },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: `
        body {
          background-image: linear-gradient(to top right, #1a0b1e, #09111d, #062338);
          background-repeat: no-repeat;
          background-attachment: fixed;
        }
      `,
    },
  },
  typography: {
    fontFamily: 'Roboto, sans-serif',
  },
});

function App() {
  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <DashboardLayout />
    </ThemeProvider>
  );
}

export default App;
