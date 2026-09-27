// Entry point for Falsora Core API
import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import { PrismaClient } from '@prisma/client';
import { PrismaPg } from '@prisma/adapter-pg';
import { Pool } from 'pg';

dotenv.config();

const app = express();
const port = process.env.PORT || 4000;

import cookieParser from 'cookie-parser';
import path from 'path';
import authRoutes from './routes/auth';
import casesRoutes from './routes/cases';
import streamsRoutes from './routes/streams';
import analyticsRoutes from './routes/analytics';
import notificationsRoutes from './routes/notifications';
import { requireAuth } from './middleware/auth';

// Middleware
app.use(cors({
  origin: (origin, callback) => {
    if (!origin || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)) {
      callback(null, true);
    } else {
      callback(null, true);
    }
  },
  credentials: true,
}));
app.use(express.json());
app.use(cookieParser());
app.use('/uploads', express.static(path.join(process.cwd(), 'uploads')));
// Grad-CAM overlays (module 6.7) are written by the ai-engine process to
// <repo root>/gradcam (falsora_ai.config.Config.paths.gradcam), not under
// core-api/uploads — serve that directory directly so heatmapUrl values
// saved by cases.ts (/gradcam/<file>.png) actually resolve.
app.use('/gradcam', express.static(path.join(__dirname, '..', '..', 'gradcam')));

import { prisma } from './db';

// Routes
app.use('/api/auth', authRoutes);                           // public
app.use('/api/cases', requireAuth, casesRoutes);            // protected
app.use('/api/streams', requireAuth, streamsRoutes);        // protected
app.use('/api/analytics', requireAuth, analyticsRoutes);   // protected
app.use('/api/notifications', requireAuth, notificationsRoutes); // protected
app.get('/health', (req, res) => {
  res.json({ status: 'ok', message: 'Falsora Core API is running!' });
});

// Start Server
app.listen(port, () => {
  console.log(`🚀 Core API Server running at http://localhost:${port}`);
});
