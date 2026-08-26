import { Navbar } from "../components/layout/Navbar";
import { EducatorSidebar } from "../components/layout/EducatorSidebar";

export default function EducatorLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <Navbar />
      <div className="flex flex-1">
        <EducatorSidebar />
        <main className="flex-1 p-6 pb-20 md:pb-6 bg-gray-50">{children}</main>
      </div>
    </div>
  );
}
