import { PrismaClient } from '@prisma/client';
import { PrismaPg } from '@prisma/adapter-pg';
import pg from 'pg';
import bcrypt from 'bcryptjs';

const { Pool } = pg;
const connectionString = process.env.DATABASE_URL;
const pool = new Pool({ connectionString });
const adapter = new PrismaPg(pool);
const prisma = new PrismaClient({ adapter });

async function main() {
  console.log('Seeding the database...');

  // 1. Create Proposal Roles: Administrator, Reviewer, User
  const adminRole = await prisma.role.upsert({
    where: { name: 'Administrator' },
    update: {},
    create: { name: 'Administrator' },
  });

  const reviewerRole = await prisma.role.upsert({
    where: { name: 'Reviewer' },
    update: {},
    create: { name: 'Reviewer' },
  });

  const userRole = await prisma.role.upsert({
    where: { name: 'User' },
    update: {},
    create: { name: 'User' },
  });

  // 2. Create Default Accounts for each role
  const adminPassword = await bcrypt.hash('admin123', 10);
  const reviewerPassword = await bcrypt.hash('reviewer123', 10);
  const userPassword = await bcrypt.hash('user123', 10);

  // Administrator Account
  const superuser = await prisma.user.upsert({
    where: { email: 'admin@falsora.ai' },
    update: { passwordHash: adminPassword, roleId: adminRole.id },
    create: {
      name: 'Falsora Admin',
      email: 'admin@falsora.ai',
      passwordHash: adminPassword,
      roleId: adminRole.id,
      isActive: true,
    },
  });

  // Backward compatibility alias admin@titli.ai
  await prisma.user.upsert({
    where: { email: 'admin@titli.ai' },
    update: { passwordHash: adminPassword, roleId: adminRole.id },
    create: {
      name: 'Ujala Zaib (Admin)',
      email: 'admin@titli.ai',
      passwordHash: adminPassword,
      roleId: adminRole.id,
      isActive: true,
    },
  });

  // Reviewer Account
  await prisma.user.upsert({
    where: { email: 'reviewer@falsora.ai' },
    update: { passwordHash: reviewerPassword, roleId: reviewerRole.id },
    create: {
      name: 'Forensic Reviewer',
      email: 'reviewer@falsora.ai',
      passwordHash: reviewerPassword,
      roleId: reviewerRole.id,
      isActive: true,
    },
  });

  // User Account
  await prisma.user.upsert({
    where: { email: 'user@falsora.ai' },
    update: { passwordHash: userPassword, roleId: userRole.id },
    create: {
      name: 'Public User',
      email: 'user@falsora.ai',
      passwordHash: userPassword,
      roleId: userRole.id,
      isActive: true,
    },
  });

  // Another User Account
  await prisma.user.upsert({
    where: { email: 'another@falsora.ai' },
    update: { passwordHash: userPassword, roleId: adminRole.id },
    create: {
      name: 'Another User',
      email: 'another@falsora.ai',
      passwordHash: userPassword,
      roleId: adminRole.id,
      isActive: true,
    },
  });

  console.log('Seeding completed successfully with proposal roles (User, Reviewer, Administrator):');
  console.log(`Administrator: admin@falsora.ai / admin123`);
  console.log(`Reviewer: reviewer@falsora.ai / reviewer123`);
  console.log(`User: user@falsora.ai / user123`);
  console.log(`Another User: another@falsora.ai / user123`);
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
