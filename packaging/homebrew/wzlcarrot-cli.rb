# Homebrew formula template. Replace homepage and sha256 for the release.
class WzlcarrotCli < Formula
  include Language::Python::Virtualenv

  desc "Multi-platform CLI (Zhihu built in): browse, publish, export, AI agent"
  homepage "https://github.com/your-org/wzlcarrot-cli"
  url "https://files.pythonhosted.org/packages/source/w/wzlcarrot-cli/wzlcarrot_cli-0.18.0.tar.gz"
  sha256 "REPLACE_WITH_SHA256"
  license "MIT"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  test do
    system bin/"wzlcarrot", "version"
  end
end
