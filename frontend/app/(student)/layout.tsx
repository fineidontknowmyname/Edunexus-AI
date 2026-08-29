import { Navbar } from "../components/layout/Navbar";
import { StudentSidebar } from "../components/layout/StudentSidebar";

export default function StudentLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <div className="flex flex-1">
        <StudentSidebar />
        <main className="flex-1 p-6 pb-20 md:pb-6 bg-app">{children}</main>
      </div>
    </div>
  );
}
