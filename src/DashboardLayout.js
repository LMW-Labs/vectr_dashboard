
import React from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import { Box, Drawer, AppBar, Toolbar, Typography, List, ListItem, ListItemButton, ListItemIcon, ListItemText, Divider } from '@mui/material';
import DashboardIcon from '@mui/icons-material/Dashboard';
import PlayCircleOutlineIcon from '@mui/icons-material/PlayCircleOutline';
import ExploreIcon from '@mui/icons-material/Explore';
import TravelExploreIcon from '@mui/icons-material/TravelExplore';
import SettingsIcon from '@mui/icons-material/Settings';
import CloudUploadIcon from '@mui/icons-material/CloudUpload';
import LogoutIcon from '@mui/icons-material/Logout';
import AccountCircleIcon from '@mui/icons-material/AccountCircle';

import DiscoverSources from './pages/DiscoverSources';
import RunAnalysis from './pages/RunAnalysis';
import ExploreInsights from './pages/ExploreInsights';
import DataUploader from './pages/DataUploader';

const drawerWidth = 240;

const menuItems = [
  { text: 'Dashboard', path: '/', icon: <DashboardIcon />, component: <Typography>Dashboard Content</Typography> },
  { text: 'Discover Sources', path: '/discover-sources', icon: <TravelExploreIcon />, component: <DiscoverSources /> },
  { text: 'Run Analysis', path: '/run-analysis', icon: <PlayCircleOutlineIcon />, component: <RunAnalysis /> },
  { text: 'Explore Insights', path: '/explore-insights', icon: <ExploreIcon />, component: <ExploreInsights /> },
  { text: 'Data Uploader', path: '/data-uploader', icon: <CloudUploadIcon />, component: <DataUploader /> },
  { text: 'Settings', path: '/settings', icon: <SettingsIcon />, component: <Typography>Settings Content</Typography> },
];

export default function DashboardLayout({ user, handleSignOut }) {
  return (
    <Box sx={{ display: 'flex' }}>
      <div style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          opacity: 0.1, 
          pointerEvents: 'none', 
          zIndex: -1,
        }}>
          <img src="/V.png" alt="V Backdrop" style={{ height: '50vh' }} />
        </div>

      <AppBar position="fixed" sx={{ zIndex: (theme) => theme.zIndex.drawer + 1, background: 'transparent', boxShadow: 'none' }}>
        <Toolbar>
          <img src="/VECTR.png" alt="Vectr Logo" style={{ height: '40px' }} />
        </Toolbar>
      </AppBar>

      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box', background: 'rgba(0,0,0,0.2)', display: 'flex', flexDirection: 'column' }, 
        }}
      >
        <Toolbar />
        <Box sx={{ overflow: 'auto', flexGrow: 1 }}>
          <List>
            {menuItems.map((item) => (
              <ListItem key={item.text} disablePadding component={Link} to={item.path} sx={{ color: 'inherit', textDecoration: 'none' }}>
                <ListItemButton>
                  <ListItemIcon sx={{ color: '#FFF' }}>{item.icon}</ListItemIcon>
                  <ListItemText primary={item.text} />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        </Box>
        <Box>
          <Divider />
          <List>
            {user && (
              <ListItem sx={{ pt: 1, pb: 1 }}>
                <ListItemIcon sx={{ color: '#FFF' }}><AccountCircleIcon /></ListItemIcon>
                <ListItemText
                  primary="Signed in as"
                  secondary={user.email}
                  primaryTypographyProps={{ fontSize: '0.8rem', color: 'text.secondary' }}
                  secondaryTypographyProps={{ fontSize: '0.9rem', color: 'text.primary' }}
                />
              </ListItem>
            )}
            <ListItem disablePadding onClick={handleSignOut}>
              <ListItemButton>
                <ListItemIcon sx={{ color: '#FFF' }}><LogoutIcon /></ListItemIcon>
                <ListItemText primary="Sign Out" />
              </ListItemButton>
            </ListItem>
          </List>
        </Box>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <Toolbar />
        <Routes>
          {menuItems.map((item) => (
            <Route key={item.path} path={item.path} element={item.component} />
          ))}
        </Routes>
      </Box>
    </Box>
  );
}
