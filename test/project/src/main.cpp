#include <vector>
template <typename T> void func() {
  std::vector<int> Numbers = {0, 1};
  const auto count = std::erase_if(Numbers, [](int N) { return N % 2 == 0; });
}
